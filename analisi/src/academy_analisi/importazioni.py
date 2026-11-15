"""File CSV di presenze e valutazioni caricati nel volume `bronze.importazioni` (ADR-0017).

Le persone dell'Academy caricano i file a mano nel volume, in una cartella per tipo
(`presenze/`, `valutazioni/`). Auto Loader li legge una volta sola ciascuno, come testo:
i tipi li controlla `qualita.py`, che mette in quarantena le righe sbagliate invece di
far fallire la lettura. Un file è solo un dato: nessun valore viene mai eseguito né
interpretato come formula o comando.

Ogni riga porta il file da cui viene e l'istante del caricamento: il verdetto del gate
vale per file. Un file ricaricato con lo stesso nome non viene riletto: un file corretto
si carica con un nome nuovo.
"""

import re

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.qualita import (
    COLONNA_CARICATA,
    COLONNA_FILE,
    COLONNE_PRESENZE,
    COLONNE_VALUTAZIONI,
)

PRESENZE, VALUTAZIONI = "presenze", "valutazioni"
COLONNE: dict[str, tuple[str, ...]] = {
    PRESENZE: COLONNE_PRESENZE,
    VALUTAZIONI: COLONNE_VALUTAZIONI,
}
# Chiave della `configuration` della pipeline con la radice del volume.
CHIAVE_CARTELLA = "academy.importazioni"
# Opzioni del lettore CSV, uguali per Auto Loader e per i test con la lettura batch.
OPZIONI_CSV = {
    "header": "true",
    # Colonne per posizione, senza confrontare l'intestazione: con `false` un'intestazione
    # diversa fa fallire la lettura e ferma lo stream per tutti i file dopo.
    "enforceSchema": "true",
    "encoding": "UTF-8",
    "pathGlobFilter": "*.csv",
}
_RADICE = re.compile(r"/Volumes/[a-z0-9_]+/[a-z0-9_]+/[a-z0-9_]+")


def schema_testo(colonne: tuple[str, ...]) -> str:
    """Schema DDL con tutte le colonne come testo: nessuna conversione in lettura."""
    return ", ".join(f"{c} STRING" for c in colonne)


def cartella(radice: str, tipo: str) -> str:
    """La cartella dei file di un tipo nel volume, con radice e tipo validati."""
    if tipo not in COLONNE:
        raise ValueError(f"Tipo di importazione sconosciuto: {tipo!r}")
    radice = radice.rstrip("/")
    if not _RADICE.fullmatch(radice):
        raise ValueError(f"Atteso /Volumes/<catalogo>/<schema>/<volume>, non {radice!r}")
    return f"{radice}/{tipo}"


def con_provenienza(righe: DataFrame) -> DataFrame:
    """Le righe con il file di origine (`_metadata.file_path`) e l'istante di caricamento."""
    return righe.select(
        "*",
        F.col("_metadata.file_path").alias(COLONNA_FILE),
        F.current_timestamp().alias(COLONNA_CARICATA),
    )


def leggi_nuovi(spark: SparkSession, radice: str, tipo: str) -> DataFrame:
    """Stream di Auto Loader sui CSV di un tipo (intestazione obbligatoria, solo `*.csv`).

    Le colonne valgono per posizione e l'intestazione si salta: un file con le colonne in
    un altro ordine o mancanti si legge lo stesso, ma le sue righe finiscono in quarantena
    (e il file è respinto). Il LEGGIMI.txt della cartella è ignorato.
    """
    righe = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .options(**OPZIONI_CSV)
        .schema(schema_testo(COLONNE[tipo]))
        .load(cartella(radice, tipo))
    )
    return con_provenienza(righe)
