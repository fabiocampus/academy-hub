"""Lettura dei CSV importati: stesse opzioni di Auto Loader, con la lettura batch."""

import sys
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession

from academy_analisi import importazioni
from academy_analisi.qualita import COLONNA_CARICATA, COLONNA_FILE, COLONNE_PRESENZE

# Leggere file con Spark su Windows richiede winutils/hadoop.dll di Hadoop: questi test
# girano in CI (Linux) e su Linux/macOS.
su_file = pytest.mark.skipif(
    sys.platform == "win32", reason="lettura di file con Spark: serve Hadoop nativo"
)


def _leggi(spark: SparkSession, cartella: Path) -> DataFrame:
    righe = (
        spark.read.format("csv")
        .options(**importazioni.OPZIONI_CSV)
        .schema(importazioni.schema_testo(COLONNE_PRESENZE))
        .load(str(cartella))
    )
    return importazioni.con_provenienza(righe)


def _scrivi(cartella: Path, nome: str, testo: str) -> Path:
    cartella.mkdir(parents=True, exist_ok=True)
    file = cartella / nome
    file.write_text(testo, encoding="utf-8", newline="\n")
    return file


@su_file
def test_righe_come_testo_con_file_e_istante(spark: SparkSession, tmp_path: Path) -> None:
    _scrivi(tmp_path, "a.csv", "edizione_id,email,giorno\n7,anna@academy.example,2026-01-02\n")

    righe = _leggi(spark, tmp_path).collect()

    assert len(righe) == 1
    assert (righe[0].edizione_id, righe[0].email, righe[0].giorno) == (
        "7",
        "anna@academy.example",
        "2026-01-02",
    )
    assert righe[0][COLONNA_FILE].endswith("/a.csv")
    assert righe[0][COLONNA_CARICATA] is not None


@su_file
def test_solo_i_file_csv(spark: SparkSession, tmp_path: Path) -> None:
    _scrivi(tmp_path, "a.csv", "edizione_id,email,giorno\n7,anna@academy.example,2026-01-02\n")
    _scrivi(tmp_path, "LEGGIMI.txt", "Carica qui i CSV.\n")

    assert {r[COLONNA_FILE].rsplit("/", 1)[-1] for r in _leggi(spark, tmp_path).collect()} == {
        "a.csv"
    }


@su_file
def test_intestazione_diversa_non_fa_fallire_la_lettura(
    spark: SparkSession, tmp_path: Path
) -> None:
    # Le colonne valgono per posizione: un file con un'intestazione sbagliata si legge
    # lo stesso e le sue righe finiscono in quarantena, invece di fermare lo stream.
    _scrivi(tmp_path, "b.csv", "email,giorno\nanna@academy.example,2026-01-02\n")

    righe = _leggi(spark, tmp_path).collect()

    assert len(righe) == 1
    assert righe[0].edizione_id == "anna@academy.example"
    assert righe[0].giorno is None


@su_file
def test_testo_pericoloso_resta_testo(spark: SparkSession, tmp_path: Path) -> None:
    _scrivi(tmp_path, "c.csv", 'edizione_id,email,giorno\n"=1+1",x@academy.example,2026-01-02\n')

    assert _leggi(spark, tmp_path).first().edizione_id == "=1+1"  # type: ignore[union-attr]


def test_cartella_per_tipo() -> None:
    assert (
        importazioni.cartella("/Volumes/academy_collaudo/bronze/importazioni/", "presenze")
        == "/Volumes/academy_collaudo/bronze/importazioni/presenze"
    )


@pytest.mark.parametrize(
    ("radice", "tipo"),
    [
        ("/Volumes/academy_collaudo/bronze/importazioni", "altro"),
        ("/tmp/importazioni", "presenze"),  # noqa: S108
        ("/Volumes/a/b/c/../d", "presenze"),
        ("", "presenze"),
    ],
)
def test_cartella_non_valida(radice: str, tipo: str) -> None:
    with pytest.raises(ValueError):
        importazioni.cartella(radice, tipo)
