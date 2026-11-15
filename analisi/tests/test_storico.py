"""Silver SCD2 da snapshot: la pipeline chiede uno snapshot alla volta, in ordine."""

from datetime import UTC, datetime

from pyspark.sql import DataFrame, SparkSession

from academy_analisi.snapshot import COLONNA_SNAPSHOT
from academy_analisi.storico import prossimo_snapshot, versione

PRIMO = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
SECONDO = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)


def _bronze(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(1, "Academy", PRIMO), (2, "Vendite", PRIMO), (1, "Academy Italia", SECONDO)],
        f"id INT, nome STRING, {COLONNA_SNAPSHOT} TIMESTAMP",
    )


def test_versione_cresce_con_l_istante() -> None:
    assert versione(PRIMO) < versione(SECONDO)
    assert versione(PRIMO) == int(PRIMO.timestamp()) * 1_000_000


def test_la_prima_chiamata_restituisce_lo_snapshot_piu_vecchio(spark: SparkSession) -> None:
    risultato = prossimo_snapshot(_bronze(spark), None)

    assert risultato is not None
    righe, v = risultato
    assert v == versione(PRIMO)
    assert sorted(r["nome"] for r in righe.collect()) == ["Academy", "Vendite"]
    # La colonna dello scatto non entra nello storico: cambierebbe a ogni snapshot.
    assert COLONNA_SNAPSHOT not in righe.columns


def test_dopo_una_versione_arriva_la_successiva(spark: SparkSession) -> None:
    risultato = prossimo_snapshot(_bronze(spark), versione(PRIMO))

    assert risultato is not None
    righe, v = risultato
    assert v == versione(SECONDO)
    assert [r["nome"] for r in righe.collect()] == ["Academy Italia"]


def test_nessuno_snapshot_nuovo(spark: SparkSession) -> None:
    assert prossimo_snapshot(_bronze(spark), versione(SECONDO)) is None


def test_bronze_vuota(spark: SparkSession) -> None:
    vuota = spark.createDataFrame([], f"id INT, {COLONNA_SNAPSHOT} TIMESTAMP")

    assert prossimo_snapshot(vuota, None) is None
