"""Controlli di qualità sulle righe importate: valide, in quarantena o bloccanti (ADR-0017)."""

from datetime import UTC, date, datetime

import pytest
from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql import functions as F

from academy_analisi.qualita import (
    COLONNE_PRESENZE,
    COLONNE_VALUTAZIONI,
    Motivo,
    classifica_presenze,
    classifica_valutazioni,
    presenze_valide,
    stato_file,
    valutazioni_valide,
)

OGGI = date(2026, 11, 20)
CARICATA = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)


def _grezze(
    spark: SparkSession, colonne: tuple[str, ...], *righe: tuple[str | None, ...]
) -> DataFrame:
    """Righe come le scrive Auto Loader: tutto testo, più file e istante del caricamento."""
    schema = ", ".join(f"{c} STRING" for c in (*colonne, "_file"))
    return spark.createDataFrame(list(righe), schema).withColumn("_caricata_il", F.lit(CARICATA))


@pytest.fixture
def persone(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(1, "anna@academy.example"), (2, "Bruno@Academy.example")], "id BIGINT, email STRING"
    )


@pytest.fixture
def edizioni(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(10, date(2026, 11, 2), date(2026, 11, 4)), (11, date(2026, 12, 1), date(2026, 12, 2))],
        "id BIGINT, data_inizio DATE, data_fine DATE",
    )


def _presenze(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame, *righe: tuple[str | None, ...]
) -> list[Row]:
    classificate = classifica_presenze(
        _grezze(spark, COLONNE_PRESENZE, *righe), persone, edizioni, F.lit(OGGI)
    )
    return classificate.orderBy("_file", "giorno", "email").collect()


def test_presenza_valida(spark: SparkSession, persone: DataFrame, edizioni: DataFrame) -> None:
    [riga] = _presenze(
        spark, persone, edizioni, ("10", "anna@academy.example", "2026-11-02", "a.csv")
    )

    assert riga.motivo is None
    assert riga.bloccante is False


def test_email_confrontata_senza_maiuscole_e_spazi(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    righe = classifica_presenze(
        _grezze(spark, COLONNE_PRESENZE, ("10", " bruno@academy.EXAMPLE ", "2026-11-03", "a.csv")),
        persone,
        edizioni,
        F.lit(OGGI),
    )

    [valida] = presenze_valide(righe).collect()
    assert valida.persona_id == 2
    assert valida.edizione_id == 10
    assert valida.giorno == date(2026, 11, 3)


@pytest.mark.parametrize(
    ("riga", "motivo", "bloccante"),
    [
        (("dieci", "anna@academy.example", "2026-11-02"), Motivo.VALORE_NON_VALIDO, False),
        (("10", "anna@academy.example", "02/11/2026"), Motivo.VALORE_NON_VALIDO, False),
        (("10", "", "2026-11-02"), Motivo.VALORE_NON_VALIDO, False),
        (("10", None, "2026-11-02"), Motivo.VALORE_NON_VALIDO, False),
        (("10", "chi@academy.example", "2026-11-02"), Motivo.PERSONA_SCONOSCIUTA, False),
        (("10", "anna@academy.example", "2026-11-05"), Motivo.FUORI_EDIZIONE, False),
        (("99", "anna@academy.example", "2026-11-02"), Motivo.EDIZIONE_INESISTENTE, True),
        (("11", "anna@academy.example", "2026-12-01"), Motivo.GIORNO_FUTURO, True),
    ],
)
def test_presenza_scartata(
    spark: SparkSession,
    persone: DataFrame,
    edizioni: DataFrame,
    riga: tuple[str | None, ...],
    motivo: Motivo,
    bloccante: bool,
) -> None:
    [classificata] = _presenze(spark, persone, edizioni, (*riga, "a.csv"))

    assert classificata.motivo == motivo
    assert classificata.bloccante is bloccante


def test_regola_bloccante_prima_delle_altre(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    # Persona sconosciuta e giorno futuro: conta il motivo che blocca il file.
    [riga] = _presenze(
        spark, persone, edizioni, ("11", "chi@academy.example", "2026-12-01", "a.csv")
    )

    assert riga.motivo == Motivo.GIORNO_FUTURO


def test_duplicato_nello_stesso_file(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    righe = _presenze(
        spark,
        persone,
        edizioni,
        ("10", "anna@academy.example", "2026-11-02", "a.csv"),
        ("10", "ANNA@academy.example", "2026-11-02", "a.csv"),
        ("10", "anna@academy.example", "2026-11-02", "b.csv"),
    )

    # Una delle due di a.csv resta valida; quella di b.csv è di un altro file.
    assert sorted((r["_file"], r.motivo or "") for r in righe) == [
        ("a.csv", ""),
        ("a.csv", Motivo.DUPLICATO),
        ("b.csv", ""),
    ]


def test_duplicato_contato_solo_fra_righe_valide(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    righe = _presenze(
        spark,
        persone,
        edizioni,
        ("10", "anna@academy.example", "2026-11-05", "a.csv"),
        ("10", "anna@academy.example", "2026-11-05", "a.csv"),
    )

    assert [r.motivo for r in righe] == [Motivo.FUORI_EDIZIONE, Motivo.FUORI_EDIZIONE]


def _valutazioni(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame, *righe: tuple[str | None, ...]
) -> list[Row]:
    classificate = classifica_valutazioni(
        _grezze(spark, COLONNE_VALUTAZIONI, *righe), persone, edizioni
    )
    return classificate.orderBy("_file", "email", "voto").collect()


def test_valutazione_valida(spark: SparkSession, persone: DataFrame, edizioni: DataFrame) -> None:
    righe = classifica_valutazioni(
        _grezze(spark, COLONNE_VALUTAZIONI, ("10", "anna@academy.example", "4", "Utile", "v.csv")),
        persone,
        edizioni,
    )

    [valida] = valutazioni_valide(righe).collect()
    assert (valida.persona_id, valida.edizione_id, valida.voto, valida.commento) == (
        1,
        10,
        4,
        "Utile",
    )


@pytest.mark.parametrize(
    ("riga", "motivo", "bloccante"),
    [
        (("10", "anna@academy.example", "quattro", None), Motivo.VALORE_NON_VALIDO, False),
        (("10", "anna@academy.example", "6", None), Motivo.VOTO_FUORI_SCALA, False),
        (("10", "anna@academy.example", "0", None), Motivo.VOTO_FUORI_SCALA, False),
        (("10", "chi@academy.example", "3", None), Motivo.PERSONA_SCONOSCIUTA, False),
        (("99", "anna@academy.example", "3", None), Motivo.EDIZIONE_INESISTENTE, True),
    ],
)
def test_valutazione_scartata(
    spark: SparkSession,
    persone: DataFrame,
    edizioni: DataFrame,
    riga: tuple[str | None, ...],
    motivo: Motivo,
    bloccante: bool,
) -> None:
    [classificata] = _valutazioni(spark, persone, edizioni, (*riga, "v.csv"))

    assert classificata.motivo == motivo
    assert classificata.bloccante is bloccante


def test_valutazioni_doppie_tutte_in_quarantena(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    # Due voti diversi della stessa persona per la stessa edizione: quale vale non si sa.
    righe = _valutazioni(
        spark,
        persone,
        edizioni,
        ("10", "anna@academy.example", "2", None, "v.csv"),
        ("10", "anna@academy.example", "5", None, "v.csv"),
    )

    assert [r.motivo for r in righe] == [Motivo.DUPLICATO, Motivo.DUPLICATO]


def _stato(spark: SparkSession, *righe: tuple[str, str | None, bool]) -> dict[str, Row]:
    controllate = spark.createDataFrame(
        [(f, m, b, CARICATA) for f, m, b in righe],
        "_file STRING, motivo STRING, bloccante BOOLEAN, _caricata_il TIMESTAMP",
    )
    return {r.file: r for r in stato_file(controllate, "presenze").collect()}


def test_file_con_poche_righe_scartate_accettato(spark: SparkSession) -> None:
    righe = [("a.csv", None, False)] * 9 + [("a.csv", Motivo.DUPLICATO, False)]

    stato = _stato(spark, *righe)["a.csv"]

    assert stato.tipo == "presenze"
    assert (stato.righe, stato.scartate, stato.bloccanti) == (10, 1, 0)
    assert stato.accettato is True
    assert stato.motivo is None


def test_file_oltre_la_soglia_di_scarto_respinto(spark: SparkSession) -> None:
    righe = [("a.csv", None, False)] * 8 + [("a.csv", Motivo.PERSONA_SCONOSCIUTA, False)] * 2

    stato = _stato(spark, *righe)["a.csv"]

    assert stato.accettato is False
    assert stato.motivo == "righe scartate 20% (oltre il 10%)"


def test_file_con_regola_bloccante_respinto(spark: SparkSession) -> None:
    righe = (
        [("a.csv", None, False)] * 30
        + [("a.csv", Motivo.GIORNO_FUTURO, True)]
        + [("a.csv", Motivo.EDIZIONE_INESISTENTE, True)] * 2
    )

    stato = _stato(spark, *righe)["a.csv"]

    assert stato.accettato is False
    assert stato.bloccanti == 3
    assert stato.motivo == "edizione_inesistente: 2 righe; giorno_futuro: 1 riga"


def test_stato_per_file(spark: SparkSession) -> None:
    stati = _stato(spark, ("a.csv", None, False), ("b.csv", Motivo.GIORNO_FUTURO, True))

    assert stati["a.csv"].accettato is True
    assert stati["b.csv"].accettato is False
