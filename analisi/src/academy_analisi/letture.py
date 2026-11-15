"""Letture di tabelle che possono non esistere ancora (prima passata, pipeline mai partita)."""

from pyspark.errors import AnalysisException
from pyspark.sql import DataFrame, SparkSession

TABELLA_ASSENTE = "TABLE_OR_VIEW_NOT_FOUND"


def leggi_o_vuota(spark: SparkSession, nome: str, schema: str) -> DataFrame:
    """La tabella, o un DataFrame vuoto con `schema` (DDL) se non esiste.

    Anche uno schema di Unity Catalog assente dà `TABLE_OR_VIEW_NOT_FOUND`: gli schemi li
    crea Terraform. Ogni altro errore (permessi, nome sbagliato) risale.

    Nella pipeline serverless py4j ammette solo alcuni metodi: `spark.catalog.tableExists`
    no (#101), e `getCondition()` passa da altre chiamate alla JVM mai provate lì. La
    condizione si legge quindi dal messaggio, già copiato quando l'errore arriva in Python.
    """
    try:
        tabella = spark.read.table(nome)
        _ = tabella.schema  # con Spark Connect la lettura è pigra: l'errore arriva qui
        return tabella
    except AnalysisException as errore:
        if f"[{TABELLA_ASSENTE}]" not in str(errore):
            raise
    return spark.createDataFrame([], schema)
