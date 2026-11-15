"""I file di esempio di data/samples/ fanno quello che dice il loro README."""

import csv
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.qualita import (
    COLONNA_CARICATA,
    COLONNA_FILE,
    COLONNE_PRESENZE,
    COLONNE_VALUTAZIONI,
    classifica_presenze,
    classifica_valutazioni,
    stato_file,
    valutazioni_valide,
)

CAMPIONI = Path(__file__).parents[2] / "data" / "samples"
OGGI = date(2026, 11, 20)


def _grezze(spark: SparkSession, nome: str, colonne: tuple[str, ...]) -> DataFrame:
    """Il CSV come lo scrive Auto Loader (testo per posizione), senza Hadoop su Windows."""
    with (CAMPIONI / nome).open(encoding="utf-8", newline="") as file:
        lettore = csv.reader(file)
        assert tuple(next(lettore)) == colonne
        righe = [(*r, nome) for r in lettore]
    schema = ", ".join(f"{c} STRING" for c in (*colonne, COLONNA_FILE))
    return spark.createDataFrame(righe, schema).withColumn(
        COLONNA_CARICATA, F.lit(datetime(2026, 11, 20, 8, tzinfo=UTC))
    )


@pytest.fixture
def persone(spark: SparkSession) -> DataFrame:
    nomi = ("ada.rossi", "bruno.verdi", "carla.neri", "dario.gallo")
    return spark.createDataFrame(
        [(i, f"{n}@academy.example") for i, n in enumerate(nomi, 1)], "id BIGINT, email STRING"
    )


@pytest.fixture
def edizioni(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(101, date(2026, 3, 2), date(2026, 3, 6)), (102, date(2026, 4, 13), date(2026, 4, 14))],
        "id BIGINT, data_inizio DATE, data_fine DATE",
    )


def test_solo_email_sintetiche() -> None:
    for file in CAMPIONI.glob("*.csv"):
        with file.open(encoding="utf-8", newline="") as f:
            email = [r["email"] for r in csv.DictReader(f)]
        assert email
        assert all(e.endswith("@academy.example") for e in email), file.name


@pytest.mark.parametrize(
    ("nome", "accettato", "motivi"),
    [
        ("presenze_pulite.csv", True, Counter[str]()),
        (
            "presenze_sporche.csv",
            False,
            Counter(
                [
                    "duplicato",
                    "giorno_futuro",
                    "persona_sconosciuta",
                    "edizione_inesistente",
                    "giorno_fuori_edizione",
                    "valore_non_valido",
                    "valore_non_valido",
                ]
            ),
        ),
    ],
)
def test_presenze(
    spark: SparkSession,
    persone: DataFrame,
    edizioni: DataFrame,
    nome: str,
    accettato: bool,
    motivi: Counter[str],
) -> None:
    classificate = classifica_presenze(
        _grezze(spark, nome, COLONNE_PRESENZE), persone, edizioni, F.lit(OGGI)
    )

    assert Counter(r.motivo for r in classificate.collect() if r.motivo) == motivi
    [stato] = stato_file(classificate, "presenze").collect()
    assert stato.accettato is accettato


@pytest.mark.parametrize(
    ("nome", "accettato", "motivi"),
    [
        ("valutazioni_pulite.csv", True, Counter[str]()),
        (
            "valutazioni_sporche.csv",
            False,
            Counter(
                [
                    "voto_fuori_scala",
                    "valore_non_valido",
                    "duplicato",
                    "duplicato",
                    "edizione_inesistente",
                    "persona_sconosciuta",
                ]
            ),
        ),
    ],
)
def test_valutazioni(
    spark: SparkSession,
    persone: DataFrame,
    edizioni: DataFrame,
    nome: str,
    accettato: bool,
    motivi: Counter[str],
) -> None:
    classificate = classifica_valutazioni(
        _grezze(spark, nome, COLONNE_VALUTAZIONI), persone, edizioni
    )

    assert Counter(r.motivo for r in classificate.collect() if r.motivo) == motivi
    [stato] = stato_file(classificate, "valutazioni").collect()
    assert stato.accettato is accettato


def test_commento_che_sembra_una_formula_resta_testo(
    spark: SparkSession, persone: DataFrame, edizioni: DataFrame
) -> None:
    classificate = classifica_valutazioni(
        _grezze(spark, "valutazioni_sporche.csv", COLONNE_VALUTAZIONI), persone, edizioni
    )

    commenti = {r.commento for r in valutazioni_valide(classificate).collect()}
    assert '=HYPERLINK("https://x.example","clic")' in commenti
