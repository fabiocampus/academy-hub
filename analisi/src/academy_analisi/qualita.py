"""Controlli di qualità sui file importati di presenze e valutazioni (ADR-0017).

Ogni riga arriva da Auto Loader come testo, con il file da cui viene (`_file`) e
l'istante del caricamento (`_caricata_il`). Qui ogni riga riceve un `motivo` (None se è
valida) e `bloccante`: le righe con un motivo vanno in quarantena; quelle con un motivo
bloccante fanno respingere l'intero file, come più del 10% di righe scartate. Un file
respinto non arriva mai nel gold (il verdetto lo fissa il gate, `gate.py`).

La persona si riconosce dall'email (i file si compilano a mano), confrontata senza
maiuscole e spazi; edizioni e persone sono quelle correnti dello storico.
"""

from enum import StrEnum

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

COLONNA_FILE = "_file"
COLONNA_CARICATA = "_caricata_il"
COLONNE_PRESENZE = ("edizione_id", "email", "giorno")
COLONNE_VALUTAZIONI = ("edizione_id", "email", "voto", "commento")
FORMATO_GIORNO = "yyyy-MM-dd"
# Oltre questa quota di righe scartate il file intero è respinto.
SOGLIA_SCARTO = 0.10
VOTO_MINIMO, VOTO_MASSIMO = 1, 5


class Motivo(StrEnum):
    VALORE_NON_VALIDO = "valore_non_valido"
    EDIZIONE_INESISTENTE = "edizione_inesistente"
    GIORNO_FUTURO = "giorno_futuro"
    PERSONA_SCONOSCIUTA = "persona_sconosciuta"
    FUORI_EDIZIONE = "giorno_fuori_edizione"
    VOTO_FUORI_SCALA = "voto_fuori_scala"
    DUPLICATO = "duplicato"


BLOCCANTI = (Motivo.EDIZIONE_INESISTENTE, Motivo.GIORNO_FUTURO)

# Colonne interne, già convertite: le usano le righe valide.
_EDIZIONE, _PERSONA, _GIORNO, _VOTO = "_edizione_id", "_persona_id", "_giorno", "_voto"
_BASE = "_motivo_base"


def _email(colonna: str) -> Column:
    return F.lower(F.trim(F.col(colonna)))


def _con_riferimenti(grezze: DataFrame, persone: DataFrame, edizioni: DataFrame) -> DataFrame:
    """Le righe con edizione ed email convertite e le anagrafiche correnti accanto."""
    p = persone.select(F.col("id").alias(_PERSONA), _email("email").alias("_email_persona"))
    e = edizioni.select(
        F.col("id").alias("_edizione_nota"),
        F.col("data_inizio").alias("_inizio"),
        F.col("data_fine").alias("_fine"),
    )
    righe = grezze.withColumn(_EDIZIONE, F.col("edizione_id").try_cast("bigint")).withColumn(
        "_email", _email("email")
    )
    return righe.join(p, righe["_email"] == p["_email_persona"], "left").join(
        e, righe[_EDIZIONE] == e["_edizione_nota"], "left"
    )


def _manca_testo(colonna: str) -> Column:
    return F.col(colonna).isNull() | (F.col(colonna) == "")


def _chiude(righe: DataFrame, motivo: Column) -> DataFrame:
    """Aggiunge `motivo` e `bloccante`, toglie le colonne di lavoro."""
    return (
        righe.withColumn("motivo", motivo)
        .withColumn("bloccante", F.coalesce(F.col("motivo").isin(*BLOCCANTI), F.lit(False)))
        .drop(_BASE, "_email", "_email_persona", "_edizione_nota", "_inizio", "_fine")
    )


def classifica_presenze(
    grezze: DataFrame, persone: DataFrame, edizioni: DataFrame, oggi: Column
) -> DataFrame:
    """Ogni presenza con il suo motivo di scarto (None se valida).

    Il primo motivo che vale è quello registrato: le regole bloccanti vengono prima delle
    altre, così un file non passa per una riga che avrebbe due difetti. Un duplicato è una
    seconda riga valida dello stesso file per la stessa persona, edizione e giorno.
    """
    righe = _con_riferimenti(grezze, persone, edizioni).withColumn(
        _GIORNO, F.try_to_date(F.col("giorno"), FORMATO_GIORNO)
    )
    base = (
        F.when(
            F.col(_EDIZIONE).isNull() | F.col(_GIORNO).isNull() | _manca_testo("_email"),
            F.lit(Motivo.VALORE_NON_VALIDO.value),
        )
        .when(F.col("_edizione_nota").isNull(), F.lit(Motivo.EDIZIONE_INESISTENTE.value))
        .when(F.col(_GIORNO) > oggi, F.lit(Motivo.GIORNO_FUTURO.value))
        .when(F.col(_PERSONA).isNull(), F.lit(Motivo.PERSONA_SCONOSCIUTA.value))
        .when(
            (F.col(_GIORNO) < F.col("_inizio")) | (F.col(_GIORNO) > F.col("_fine")),
            F.lit(Motivo.FUORI_EDIZIONE.value),
        )
    )
    righe = righe.withColumn(_BASE, base)
    stessa = Window.partitionBy(
        COLONNA_FILE, _EDIZIONE, _PERSONA, _GIORNO, F.col(_BASE).isNull()
    ).orderBy(COLONNA_CARICATA)
    motivo = F.when(
        F.col(_BASE).isNull() & (F.row_number().over(stessa) > 1),
        F.lit(Motivo.DUPLICATO.value),
    ).otherwise(F.col(_BASE))
    return _chiude(righe, motivo)


def classifica_valutazioni(grezze: DataFrame, persone: DataFrame, edizioni: DataFrame) -> DataFrame:
    """Ogni valutazione con il suo motivo di scarto (None se valida).

    Due valutazioni valide della stessa persona per la stessa edizione nello stesso file
    vanno entrambe in quarantena: quale delle due valga non si può sapere.
    """
    righe = _con_riferimenti(grezze, persone, edizioni).withColumn(
        _VOTO, F.col("voto").try_cast("int")
    )
    base = (
        F.when(
            F.col(_EDIZIONE).isNull() | F.col(_VOTO).isNull() | _manca_testo("_email"),
            F.lit(Motivo.VALORE_NON_VALIDO.value),
        )
        .when(F.col("_edizione_nota").isNull(), F.lit(Motivo.EDIZIONE_INESISTENTE.value))
        .when(F.col(_PERSONA).isNull(), F.lit(Motivo.PERSONA_SCONOSCIUTA.value))
        .when(
            ~F.col(_VOTO).between(VOTO_MINIMO, VOTO_MASSIMO),
            F.lit(Motivo.VOTO_FUORI_SCALA.value),
        )
    )
    righe = righe.withColumn(_BASE, base)
    stessa = Window.partitionBy(COLONNA_FILE, _EDIZIONE, _PERSONA, F.col(_BASE).isNull())
    motivo = F.when(
        F.col(_BASE).isNull() & (F.count(F.lit(1)).over(stessa) > 1),
        F.lit(Motivo.DUPLICATO.value),
    ).otherwise(F.col(_BASE))
    return _chiude(righe, motivo)


def presenze_valide(classificate: DataFrame) -> DataFrame:
    """Le presenze senza motivo di scarto, con i tipi del dominio."""
    return classificate.where(F.col("motivo").isNull()).select(
        COLONNA_FILE,
        COLONNA_CARICATA,
        F.col(_EDIZIONE).alias("edizione_id"),
        F.col(_PERSONA).alias("persona_id"),
        F.col(_GIORNO).alias("giorno"),
    )


def valutazioni_valide(classificate: DataFrame) -> DataFrame:
    """Le valutazioni senza motivo di scarto, con i tipi del dominio."""
    commento = F.trim(F.col("commento"))
    return classificate.where(F.col("motivo").isNull()).select(
        COLONNA_FILE,
        COLONNA_CARICATA,
        F.col(_EDIZIONE).alias("edizione_id"),
        F.col(_PERSONA).alias("persona_id"),
        F.col(_VOTO).alias("voto"),
        F.when(commento == "", None).otherwise(commento).alias("commento"),
    )


def quarantena(classificate: DataFrame, colonne: tuple[str, ...]) -> DataFrame:
    """Le righe scartate, come sono arrivate, con il motivo."""
    return classificate.where(F.col("motivo").isNotNull()).select(
        COLONNA_FILE, COLONNA_CARICATA, *colonne, "motivo", "bloccante"
    )


def stato_file(controllate: DataFrame, tipo: str) -> DataFrame:
    """Per ogni file: righe, scartate, bloccanti, se è accettato e perché no.

    Il motivo elenca le regole bloccanti violate (in ordine di nome) e la quota di righe
    scartate se supera la soglia; None per un file accettato.
    """
    totali = controllate.groupBy(COLONNA_FILE).agg(
        F.min(COLONNA_CARICATA).alias("caricato_il"),
        F.count(F.lit(1)).alias("righe"),
        F.count("motivo").alias("scartate"),
        F.count(F.when(F.col("bloccante"), 1)).alias("bloccanti"),
    )
    per_regola = (
        controllate.where(F.col("bloccante"))
        .groupBy(COLONNA_FILE, "motivo")
        .agg(F.count(F.lit(1)).alias("n"))
        .select(
            COLONNA_FILE,
            F.struct(
                F.col("motivo"),
                F.concat(
                    F.col("motivo"),
                    F.lit(": "),
                    F.col("n").cast("string"),
                    F.when(F.col("n") == 1, F.lit(" riga")).otherwise(F.lit(" righe")),
                ).alias("testo"),
            ).alias("regola"),
        )
        .groupBy(COLONNA_FILE)
        .agg(F.array_sort(F.collect_list("regola")).alias("regole"))
    )
    quota = F.col("scartate") / F.col("righe")
    oltre = F.when(
        quota > SOGLIA_SCARTO,
        F.concat(
            F.lit("righe scartate "),
            F.round(quota * 100).cast("int").cast("string"),
            F.lit(f"% (oltre il {round(SOGLIA_SCARTO * 100)}%)"),
        ),
    )
    testo = F.concat_ws(
        "; ", F.array_join(F.transform(F.col("regole"), lambda r: r["testo"]), "; "), oltre
    )
    return totali.join(per_regola, COLONNA_FILE, "left").select(
        F.col(COLONNA_FILE).alias("file"),
        F.lit(tipo).alias("tipo"),
        "caricato_il",
        "righe",
        "scartate",
        "bloccanti",
        ((F.col("bloccanti") == 0) & (quota <= SOGLIA_SCARTO)).alias("accettato"),
        F.when(testo == "", None).otherwise(testo).alias("motivo"),
    )
