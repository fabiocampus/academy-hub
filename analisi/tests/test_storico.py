"""Silver SCD2 da snapshot: la pipeline chiede uno snapshot alla volta, in ordine."""

from datetime import UTC, datetime

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.catalog import Catalog

from academy_analisi.snapshot import COLONNA_SNAPSHOT
from academy_analisi.storico import leggi_scatti, prossimo_snapshot, versione

PRIMO = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
# Con i microsecondi: la versione calcolata da Spark (unix_micros) deve coincidere.
SECONDO = datetime(2026, 11, 15, 5, 0, 0, 123456, tzinfo=UTC)
TERZO = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)


def _scatti(spark: SparkSession, *istanti: datetime) -> DataFrame:
    return spark.createDataFrame([(i,) for i in istanti], f"{COLONNA_SNAPSHOT} TIMESTAMP")


def _vuota(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame([], f"id INT, nome STRING, {COLONNA_SNAPSHOT} TIMESTAMP")


def _bronze(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(1, "Academy", PRIMO), (2, "Vendite", PRIMO), (1, "Academy Italia", SECONDO)],
        f"id INT, nome STRING, {COLONNA_SNAPSHOT} TIMESTAMP",
    )


def test_versione_cresce_con_l_istante() -> None:
    assert versione(PRIMO) < versione(SECONDO)
    assert versione(PRIMO) == int(PRIMO.timestamp()) * 1_000_000
    assert versione(SECONDO) == int(SECONDO.timestamp()) * 1_000_000 + 123456


def test_la_prima_chiamata_restituisce_lo_snapshot_piu_vecchio(spark: SparkSession) -> None:
    risultato = prossimo_snapshot(_bronze(spark), _scatti(spark, PRIMO, SECONDO), None)

    assert risultato is not None
    righe, v = risultato
    assert v == versione(PRIMO)
    assert sorted(r["nome"] for r in righe.collect()) == ["Academy", "Vendite"]
    # La colonna dello scatto non entra nello storico: cambierebbe a ogni snapshot.
    assert COLONNA_SNAPSHOT not in righe.columns


def test_dopo_una_versione_arriva_la_successiva(spark: SparkSession) -> None:
    risultato = prossimo_snapshot(_bronze(spark), _scatti(spark, PRIMO, SECONDO), versione(PRIMO))

    assert risultato is not None
    righe, v = risultato
    assert v == versione(SECONDO)
    assert [r["nome"] for r in righe.collect()] == ["Academy Italia"]


def test_nessuno_snapshot_nuovo(spark: SparkSession) -> None:
    assert (
        prossimo_snapshot(_bronze(spark), _scatti(spark, PRIMO, SECONDO), versione(SECONDO)) is None
    )


def test_nessuno_scatto(spark: SparkSession) -> None:
    assert prossimo_snapshot(_vuota(spark), _scatti(spark), None) is None


def test_primo_scatto_di_una_tabella_vuota(spark: SparkSession) -> None:
    # #99: in produzione corsi era vuota, la sorgente restituiva None e la pipeline falliva.
    risultato = prossimo_snapshot(_vuota(spark), _scatti(spark, PRIMO), None)

    assert risultato is not None
    righe, v = risultato
    assert v == versione(PRIMO)
    assert righe.collect() == []
    assert righe.columns == ["id", "nome"]


def test_tabella_svuotata_da_uno_snapshot_vuoto(spark: SparkSession) -> None:
    # Dopo SECONDO la tabella si è svuotata: lo snapshot vuoto chiude le righe aperte.
    risultato = prossimo_snapshot(
        _bronze(spark), _scatti(spark, PRIMO, SECONDO, TERZO), versione(SECONDO)
    )

    assert risultato is not None
    righe, v = risultato
    assert v == versione(TERZO)
    assert righe.collect() == []


def test_snapshot_precedenti_al_registro_restano_validi(spark: SparkSession) -> None:
    # Bronze scritta prima di `scatti`: una pipeline ricreata rilegge anche quegli snapshot.
    risultato = prossimo_snapshot(_bronze(spark), _scatti(spark, TERZO), None)

    assert risultato is not None
    assert risultato[1] == versione(PRIMO)


def test_bronze_prima_del_registro_poi_scatto_vuoto(spark: SparkSession) -> None:
    # Collaudo dopo il rilascio: PRIMO solo in bronze, SECONDO solo nel registro (vuota).
    bronze = spark.createDataFrame(
        [(1, "Corso", PRIMO)], f"id INT, nome STRING, {COLONNA_SNAPSHOT} TIMESTAMP"
    )
    scatti = _scatti(spark, SECONDO)

    primo = prossimo_snapshot(bronze, scatti, None)
    assert primo is not None
    assert primo[1] == versione(PRIMO)
    secondo = prossimo_snapshot(bronze, scatti, primo[1])
    assert secondo is not None
    assert secondo[1] == versione(SECONDO)
    assert secondo[0].collect() == []
    assert prossimo_snapshot(bronze, scatti, secondo[1]) is None


def test_registro_non_ancora_creato(spark: SparkSession, monkeypatch: pytest.MonkeyPatch) -> None:
    # Il catalogo vero passa da Hadoop, che sulla Java della CI non va (getSubject):
    # qui conta solo il ramo senza tabella.
    def nessuna(_self: Catalog, _nome: str) -> bool:
        return False

    monkeypatch.setattr(Catalog, "tableExists", nessuna)

    scatti = leggi_scatti(spark, "academy_collaudo.bronze.scatti")

    assert scatti.columns == [COLONNA_SNAPSHOT]
    assert scatti.collect() == []
