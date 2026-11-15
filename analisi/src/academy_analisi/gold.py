"""Gold dei report: dallo storico in silver e dalle importazioni accettate (ADR-0017).

`Completata` esiste solo qui (ADR-0016 §8): un'iscrizione `Confermata` di un'edizione
conclusa e non cancellata è completata se le giornate con una presenza sono almeno la
soglia (percentuale intera, 75 di difetto) delle giornate dell'edizione, contate dal primo
all'ultimo giorno compresi. Il team di una persona è quello che aveva alla fine
dell'edizione, letto dallo storico SCD 2; se lo storico comincia dopo, vale la prima
versione nota.

Il gold si riscrive per intero a ogni passata riuscita del gate: le tabelle sono piccole
e così non restano righe di file respinti o di dati poi corretti.
"""

import argparse
from collections.abc import Callable, Sequence

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from academy_analisi.gate import SCHEMA_VERDETTI, VERDETTI
from academy_analisi.letture import leggi_o_vuota
from academy_analisi.snapshot import nome_tabella

INIZIO, FINE = "__START_AT", "__END_AT"
STATI_CONCLUDIBILI = ("Confermata", "Completata")
SOGLIA_COMPLETAMENTO = 75


def correnti(storico: DataFrame) -> DataFrame:
    """Le righe ancora valide dello storico, senza le colonne dello SCD 2."""
    return storico.where(F.col(FINE).isNull()).drop(INIZIO, FINE)


def _team_alla_fine(iscrizioni: DataFrame, persone: DataFrame) -> DataFrame:
    """`team_id` della persona alla fine dell'edizione (inizio del giorno dopo, in UTC).

    Fra le versioni della persona vale l'ultima cominciata entro quell'istante; se non
    ce n'è (storico più recente dell'edizione), la prima.
    """
    istante = F.unix_micros(F.to_timestamp(F.date_add(F.col("data_fine"), 1)))
    versioni = persone.select(
        F.col("id").alias("_persona"), F.col("team_id"), F.col(INIZIO).alias("_dal")
    )
    candidate = iscrizioni.join(versioni, iscrizioni["persona_id"] == versioni["_persona"])
    entro = F.col("_dal") <= istante
    ordine = Window.partitionBy("iscrizione_id").orderBy(
        F.when(entro, 0).otherwise(1),
        F.when(entro, -F.col("_dal")).otherwise(F.col("_dal")),
    )
    return (
        candidate.withColumn("_n", F.row_number().over(ordine))
        .where(F.col("_n") == 1)
        .drop("_n", "_persona", "_dal")
    )


def iscrizioni_concluse(
    *,
    iscrizioni: DataFrame,
    edizioni: DataFrame,
    persone: DataFrame,
    presenze: DataFrame,
    oggi: Column,
    soglia: int = SOGLIA_COMPLETAMENTO,
) -> DataFrame:
    """Una riga per iscrizione di un'edizione conclusa, con le presenze e `completata`.

    `iscrizioni`, `edizioni` e `persone` sono lo storico SCD 2; `presenze` le righe valide
    dei file accettati (persona_id, edizione_id, giorno): un giorno ripetuto conta una volta.
    """
    if not 0 < soglia <= 100:
        raise ValueError(f"Soglia di completamento in percentuale (1-100), non {soglia}")
    isc = correnti(iscrizioni).where(F.col("stato").isin(*STATI_CONCLUDIBILI))
    ed = (
        correnti(edizioni)
        .where(F.col("cancellata_il").isNull() & (F.col("data_fine") < oggi))
        .select(
            F.col("id").alias("_edizione"),
            "corso_id",
            "data_inizio",
            "data_fine",
            (F.datediff("data_fine", "data_inizio") + 1).alias("giornate"),
        )
    )
    presenti = presenze.groupBy("persona_id", "edizione_id").agg(
        F.count_distinct("giorno").alias("_presenti")
    )
    base = isc.join(ed, isc["edizione_id"] == ed["_edizione"]).select(
        F.col("id").alias("iscrizione_id"),
        "persona_id",
        "edizione_id",
        "corso_id",
        "data_inizio",
        "data_fine",
        "giornate",
    )
    con_presenze = base.join(presenti, ["persona_id", "edizione_id"], "left").withColumn(
        "giorni_presenti", F.coalesce(F.col("_presenti"), F.lit(0))
    )
    completata = F.col("giorni_presenti") * 100 >= F.col("giornate") * soglia
    return _team_alla_fine(con_presenze, persone).select(
        "iscrizione_id",
        "persona_id",
        "team_id",
        "edizione_id",
        "corso_id",
        "data_inizio",
        "data_fine",
        "giornate",
        "giorni_presenti",
        completata.alias("completata"),
    )


def ore_per_team(concluse: DataFrame, corsi: DataFrame, team: DataFrame) -> DataFrame:
    """Ore di formazione per team: somma della durata dei corsi completati."""
    c = corsi.select(F.col("id").alias("corso_id"), "durata_ore")
    t = team.select(F.col("id").alias("team_id"), F.col("nome").alias("team"))
    return (
        concluse.where(F.col("completata"))
        .join(c, "corso_id")
        .groupBy("team_id")
        .agg(
            F.sum("durata_ore").cast("bigint").alias("ore_formazione"),
            F.count(F.lit(1)).alias("iscrizioni_completate"),
        )
        .join(t, "team_id", "left")
        .select("team_id", "team", "ore_formazione", "iscrizioni_completate")
    )


def tasso_completamento(concluse: DataFrame, corsi: DataFrame) -> DataFrame:
    """Per corso: iscrizioni concluse, completate e il loro rapporto (4 decimali)."""
    c = corsi.select(F.col("id").alias("corso_id"), "titolo")
    return (
        concluse.groupBy("corso_id")
        .agg(
            F.count(F.lit(1)).alias("concluse"),
            F.count(F.when(F.col("completata"), 1)).alias("completate"),
        )
        .withColumn("tasso", F.round(F.col("completate") / F.col("concluse"), 4))
        .join(c, "corso_id", "left")
        .select("corso_id", "titolo", "concluse", "completate", "tasso")
    )


def valutazione_media(valutazioni: DataFrame, concluse: DataFrame, corsi: DataFrame) -> DataFrame:
    """Per corso: numero di valutazioni e voto medio (2 decimali).

    Contano solo le valutazioni di iscrizioni completate, una per iscrizione: la prima
    caricata (la valutazione non si modifica, D6).
    """
    prima = Window.partitionBy("persona_id", "edizione_id").orderBy("_caricata_il", "_file")
    uniche = (
        valutazioni.withColumn("_n", F.row_number().over(prima))
        .where(F.col("_n") == 1)
        .select("persona_id", "edizione_id", "voto")
    )
    completate = concluse.where(F.col("completata")).select("persona_id", "edizione_id", "corso_id")
    c = corsi.select(F.col("id").alias("corso_id"), "titolo")
    return (
        uniche.join(completate, ["persona_id", "edizione_id"])
        .groupBy("corso_id")
        .agg(
            F.count(F.lit(1)).alias("valutazioni"),
            F.round(F.avg("voto"), 2).alias("voto_medio"),
        )
        .join(c, "corso_id", "left")
        .select("corso_id", "titolo", "valutazioni", "voto_medio")
    )


def da_file_accettati(righe: DataFrame, verdetti: DataFrame, tipo: str) -> DataFrame:
    """Le righe dei soli file di quel tipo che il gate ha accettato."""
    accettati = verdetti.where((F.col("tipo") == tipo) & F.col("accettato")).select(
        F.col("file").alias("_file")
    )
    return righe.join(accettati, "_file", "left_semi")


def aggiorna(
    *,
    leggi: Callable[[str], DataFrame],
    scrivi: Callable[[DataFrame, str], None],
    silver: str,
    qualita: str,
    gold: str,
    oggi: Column,
    soglia: int = SOGLIA_COMPLETAMENTO,
) -> dict[str, DataFrame]:
    """Calcola e scrive le tabelle gold; restituisce quelle scritte, per nome.

    Presenze e valutazioni vengono solo dai file che il gate ha accettato.
    """
    verdetti = leggi(nome_tabella(qualita, VERDETTI))
    concluse = iscrizioni_concluse(
        iscrizioni=leggi(nome_tabella(silver, "iscrizioni")),
        edizioni=leggi(nome_tabella(silver, "edizioni")),
        persone=leggi(nome_tabella(silver, "persone")),
        presenze=da_file_accettati(leggi(nome_tabella(silver, "presenze")), verdetti, "presenze"),
        oggi=oggi,
        soglia=soglia,
    )
    corsi = correnti(leggi(nome_tabella(silver, "corsi")))
    team = correnti(leggi(nome_tabella(silver, "team")))
    valutazioni = da_file_accettati(
        leggi(nome_tabella(silver, "valutazioni")), verdetti, "valutazioni"
    )
    tabelle = {
        "iscrizioni_concluse": concluse,
        "ore_per_team": ore_per_team(concluse, corsi, team),
        "tasso_completamento": tasso_completamento(concluse, corsi),
        "valutazione_media": valutazione_media(valutazioni, concluse, corsi),
    }
    for nome, righe in tabelle.items():
        scrivi(righe, nome_tabella(gold, nome))
    return tabelle


def lettore(spark: SparkSession, qualita: str) -> Callable[[str], DataFrame]:
    """Legge le tabelle per `aggiorna`; i verdetti possono mancare (nessun CSV ancora).

    `gate.controlla` crea `qualita.verdetti` solo al primo file: senza, il gold vale per
    lo storico e nessuna presenza o valutazione.
    """
    verdetti = nome_tabella(qualita, VERDETTI)

    def leggi(nome: str) -> DataFrame:
        if nome == verdetti:
            return leggi_o_vuota(spark, nome, SCHEMA_VERDETTI)
        return spark.read.table(nome)

    return leggi


def sovrascrivi(righe: DataFrame, nome: str) -> None:
    """Riscrive la tabella Delta (schema compreso): il gold si ricalcola per intero."""
    righe.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(nome)


def main(argv: Sequence[str] | None = None) -> int:
    argomenti = argparse.ArgumentParser(description="Aggiorna il gold dei report")
    argomenti.add_argument("--silver", required=True, help="catalogo.schema dello storico")
    argomenti.add_argument("--qualita", required=True, help="catalogo.schema della qualità")
    argomenti.add_argument("--gold", required=True, help="catalogo.schema del gold")
    argomenti.add_argument(
        "--soglia", type=int, default=SOGLIA_COMPLETAMENTO, help="soglia di completamento (%%)"
    )
    a = argomenti.parse_args(argv)
    for schema in (a.silver, a.qualita, a.gold):
        nome_tabella(schema, "x")  # nomi non validi fermano il task prima di Spark

    spark = SparkSession.builder.getOrCreate()
    tabelle = aggiorna(
        leggi=lettore(spark, a.qualita),
        scrivi=sovrascrivi,
        silver=a.silver,
        qualita=a.qualita,
        gold=a.gold,
        oggi=F.current_date(),
        soglia=a.soglia,
    )
    for nome in tabelle:
        print(f"{a.gold}.{nome}: {spark.read.table(nome_tabella(a.gold, nome)).count()} righe")
    return 0
