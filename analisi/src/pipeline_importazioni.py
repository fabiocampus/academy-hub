"""Pipeline Lakeflow `storico`, seconda libreria: importazioni e controlli (ADR-0017).

Auto Loader legge i CSV del volume in `bronze.presenze_importate` e
`bronze.valutazioni_importate` (streaming table, una riga letta una volta). Le viste
materializzate classificano ogni riga con le anagrafiche correnti dello storico della
stessa pipeline (`silver.persone`, `silver.edizioni`): valide in silver, scartate in
`qualita.*_quarantena`, lo stato di ogni file in `qualita.file_importati`, che il task
`controlli` del job trasforma in verdetto. La logica sta in academy_analisi (testata con
Spark locale); qui ci sono solo le dichiarazioni.

La radice del volume arriva dalla `configuration` della pipeline (`academy.importazioni`).
Niente `spark.catalog.tableExists` né `getCondition()` (#101): py4j non li ammette.
"""
# pyright: reportAttributeAccessIssue=false

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.gold import correnti
from academy_analisi.importazioni import (
    CHIAVE_CARTELLA,
    PRESENZE,
    VALUTAZIONI,
    leggi_nuovi,
)
from academy_analisi.qualita import (
    COLONNE_PRESENZE,
    COLONNE_VALUTAZIONI,
    classifica_presenze,
    classifica_valutazioni,
    presenze_valide,
    quarantena,
    stato_file,
    valutazioni_valide,
)


def _spark() -> SparkSession:
    return SparkSession.active()


def _radice() -> str:
    radice = _spark().conf.get(CHIAVE_CARTELLA, None)
    if not radice:
        raise ValueError(f"Manca {CHIAVE_CARTELLA} nella configuration della pipeline")
    return radice


@dp.table(
    name="bronze.presenze_importate",
    comment="Righe dei CSV di presenze caricati nel volume, come testo (Auto Loader)",
)
def presenze_importate() -> DataFrame:
    return leggi_nuovi(_spark(), _radice(), PRESENZE)


@dp.table(
    name="bronze.valutazioni_importate",
    comment="Righe dei CSV di valutazioni caricati nel volume, come testo (Auto Loader)",
)
def valutazioni_importate() -> DataFrame:
    return leggi_nuovi(_spark(), _radice(), VALUTAZIONI)


def _presenze_classificate() -> DataFrame:
    spark = _spark()
    return classifica_presenze(
        spark.read.table("bronze.presenze_importate"),
        correnti(spark.read.table("persone")),
        correnti(spark.read.table("edizioni")),
        F.current_date(),
    )


def _valutazioni_classificate() -> DataFrame:
    spark = _spark()
    return classifica_valutazioni(
        spark.read.table("bronze.valutazioni_importate"),
        correnti(spark.read.table("persone")),
        correnti(spark.read.table("edizioni")),
    )


@dp.materialized_view(
    name="presenze", comment="Presenze valide dei file importati (il gold usa solo gli accettati)"
)
def presenze() -> DataFrame:
    return presenze_valide(_presenze_classificate())


@dp.materialized_view(
    name="valutazioni",
    comment="Valutazioni valide dei file importati (il gold usa solo gli accettati)",
)
def valutazioni() -> DataFrame:
    return valutazioni_valide(_valutazioni_classificate())


@dp.materialized_view(
    name="qualita.presenze_quarantena", comment="Presenze scartate, con il motivo"
)
def presenze_quarantena() -> DataFrame:
    return quarantena(_presenze_classificate(), COLONNE_PRESENZE)


@dp.materialized_view(
    name="qualita.valutazioni_quarantena", comment="Valutazioni scartate, con il motivo"
)
def valutazioni_quarantena() -> DataFrame:
    return quarantena(_valutazioni_classificate(), COLONNE_VALUTAZIONI)


@dp.materialized_view(
    name="qualita.file_importati",
    comment="Stato di ogni file importato: righe, scartate, accettato o perché no",
)
def file_importati() -> DataFrame:
    return stato_file(_presenze_classificate(), PRESENZE).unionByName(
        stato_file(_valutazioni_classificate(), VALUTAZIONI)
    )
