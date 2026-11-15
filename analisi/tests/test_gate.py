"""Gate di qualità: verdetto fissato per file, blocco del gold, esito della passata."""

from datetime import UTC, datetime

import pytest
from pyspark.sql import DataFrame, SparkSession

from academy_analisi.gate import (
    SCHEMA_STATO,
    SCHEMA_VERDETTI,
    Esito,
    FileRespintiError,
    Respinto,
    controlla,
    esito_passata,
    motivo_blocco,
)

ISTANTE = datetime(2026, 11, 20, 5, 30, tzinfo=UTC)
CARICATO = datetime(2026, 11, 20, 5, 10, tzinfo=UTC)
CARTELLA = "/Volumes/academy_collaudo/bronze/importazioni"


def _stato(spark: SparkSession, *righe: tuple[str, str, bool, str | None]) -> DataFrame:
    return spark.createDataFrame(
        [(f, t, CARICATO, 10, 0 if a else 3, 0, a, m) for f, t, a, m in righe], SCHEMA_STATO
    )


def _verdetti(spark: SparkSession, *file: tuple[str, str, bool]) -> DataFrame:
    return spark.createDataFrame(
        [(f, t, a, None, 10, 0, 1, ISTANTE) for f, t, a in file], SCHEMA_VERDETTI
    )


class _Registro:
    def __init__(self) -> None:
        self.scritte: list[DataFrame] = []

    def __call__(self, righe: DataFrame) -> None:
        self.scritte.append(righe)


def test_nuovi_file_accettati(spark: SparkSession) -> None:
    registro = _Registro()

    respinti = controlla(
        spark=spark,
        stato=_stato(spark, (f"{CARTELLA}/presenze/a.csv", "presenze", True, None)),
        verdetti=_verdetti(spark),
        scrivi=registro,
        run_id=7,
        istante=ISTANTE,
    )

    assert respinti == []
    [scritte] = registro.scritte
    [verdetto] = scritte.collect()
    assert (verdetto.file, verdetto.accettato, verdetto.run_id) == (
        f"{CARTELLA}/presenze/a.csv",
        True,
        7,
    )


def test_file_gia_valutato_non_cambia_verdetto(spark: SparkSession) -> None:
    # Respinto ieri per un giorno futuro: oggi quel giorno è passato, ma resta respinto.
    registro = _Registro()
    file = f"{CARTELLA}/presenze/a.csv"

    respinti = controlla(
        spark=spark,
        stato=_stato(spark, (file, "presenze", True, None)),
        verdetti=_verdetti(spark, (file, "presenze", False)),
        scrivi=registro,
        run_id=8,
        istante=ISTANTE,
    )

    assert respinti == []
    assert registro.scritte == []


def test_ritentativo_della_stessa_run_resta_bloccato(spark: SparkSession) -> None:
    # Il serverless ritenta `controlli`: il file respinto al primo tentativo non è più
    # nuovo, ma il gate deve bloccare ancora.
    registro = _Registro()
    file = f"{CARTELLA}/presenze/sporco.csv"

    respinti = controlla(
        spark=spark,
        stato=_stato(spark, (file, "presenze", False, "giorno_futuro: 1 riga")),
        verdetti=spark.createDataFrame(
            [(file, "presenze", False, "giorno_futuro: 1 riga", 10, 3, 8, ISTANTE)],
            SCHEMA_VERDETTI,
        ),
        scrivi=registro,
        run_id=8,
        istante=ISTANTE,
    )

    assert respinti == [Respinto(file=file, tipo="presenze", motivo="giorno_futuro: 1 riga")]
    assert registro.scritte == []


def test_stesso_nome_di_tipo_diverso_e_un_altro_file(spark: SparkSession) -> None:
    registro = _Registro()

    controlla(
        spark=spark,
        stato=_stato(spark, ("a.csv", "valutazioni", True, None)),
        verdetti=_verdetti(spark, ("a.csv", "presenze", True)),
        scrivi=registro,
        run_id=8,
        istante=ISTANTE,
    )

    assert len(registro.scritte) == 1


def test_file_nuovo_respinto(spark: SparkSession) -> None:
    registro = _Registro()
    file = f"{CARTELLA}/presenze/sporco.csv"

    respinti = controlla(
        spark=spark,
        stato=_stato(
            spark,
            (file, "presenze", False, "giorno_futuro: 1 riga"),
            (f"{CARTELLA}/presenze/pulito.csv", "presenze", True, None),
        ),
        verdetti=_verdetti(spark),
        scrivi=registro,
        run_id=9,
        istante=ISTANTE,
    )

    assert respinti == [Respinto(file=file, tipo="presenze", motivo="giorno_futuro: 1 riga")]
    # Il verdetto si scrive anche per il file respinto, prima che il gate blocchi.
    assert len(registro.scritte[0].collect()) == 2


def test_motivo_blocco_col_nome_del_file() -> None:
    respinti = [
        Respinto(
            file=f"{CARTELLA}/presenze/a.csv", tipo="presenze", motivo="giorno_futuro: 1 riga"
        ),
        Respinto(file=f"{CARTELLA}/valutazioni/b.csv", tipo="valutazioni", motivo="x"),
    ]

    assert motivo_blocco(respinti) == "presenze a.csv: giorno_futuro: 1 riga; valutazioni b.csv: x"


def test_gate_bloccato_porta_il_motivo() -> None:
    errore = FileRespintiError([Respinto(file="a.csv", tipo="presenze", motivo="m")])

    assert "presenze a.csv: m" in str(errore)


@pytest.mark.parametrize(
    ("respinti", "controlli", "gold", "atteso"),
    [
        ([], "success", "success", (Esito.AGGIORNATO, None)),
        (
            [Respinto(file="a.csv", tipo="presenze", motivo="m")],
            "failed",
            "upstream_failed",
            (Esito.BLOCCATO, "presenze a.csv: m"),
        ),
        ([], "failed", "upstream_failed", (Esito.ERRORE, "controlli failed, gold upstream_failed")),
        (
            [],
            "upstream_failed",
            "upstream_failed",
            (Esito.ERRORE, "controlli upstream_failed, gold upstream_failed"),
        ),
        ([], "success", "failed", (Esito.ERRORE, "controlli success, gold failed")),
    ],
)
def test_esito_della_passata(
    respinti: list[Respinto], controlli: str, gold: str, atteso: tuple[Esito, str | None]
) -> None:
    assert esito_passata(respinti, controlli, gold) == atteso
