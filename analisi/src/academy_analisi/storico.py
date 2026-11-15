"""Storico in silver dagli snapshot di bronze: SCD di tipo 2 (ADR-0016).

La pipeline usa `create_auto_cdc_from_snapshot_flow` con una funzione come sorgente:
riceve l'ultima versione già elaborata e restituisce lo snapshot successivo, oppure
None quando non ce ne sono altri. Così uno snapshot saltato (pipeline fallita) viene
recuperato alla passata dopo, in ordine. La versione è l'istante dello scatto in
microsecondi: intera, crescente, uguale per tutte le tabelle della stessa passata.

Le versioni vengono dal registro `bronze.scatti`, non solo dalle righe della tabella: lo
snapshot di una tabella vuota non ha righe ma va elaborato lo stesso, altrimenti la
prima passata fallisce e una tabella svuotata non chiude mai le sue righe (#99).
"""

from datetime import datetime

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from academy_analisi.snapshot import COLONNA_SNAPSHOT

_VERSIONE = "_versione"


def versione(istante: datetime) -> int:
    """Microsecondi dall'epoch dell'istante dello scatto.

    La regola della versione, scritta in Python; `prossimo_snapshot` la calcola in Spark
    con `unix_micros` e i test controllano che le due coincidano.
    """
    secondi = int(istante.timestamp())
    return secondi * 1_000_000 + istante.microsecond


def prossimo_snapshot(
    bronze: DataFrame, scatti: DataFrame, ultima: int | None
) -> tuple[DataFrame, int] | None:
    """Lo snapshot dopo `ultima` (il primo se None), senza la colonna dello scatto.

    Le versioni sono quelle del registro più quelle già in bronze (snapshot scritti prima
    del registro). Le righe restituite possono essere zero: tabella vuota a quello scatto.
    """
    con_versione = bronze.withColumn(_VERSIONE, F.unix_micros(F.col(COLONNA_SNAPSHOT)))
    versioni = scatti.select(F.unix_micros(F.col(COLONNA_SNAPSHOT)).alias(_VERSIONE)).union(
        con_versione.select(_VERSIONE)
    )
    candidate = versioni if ultima is None else versioni.where(F.col(_VERSIONE) > ultima)
    prima = candidate.agg(F.min(_VERSIONE)).first()
    if prima is None or prima[0] is None:
        return None
    prossima = int(prima[0])
    righe = con_versione.where(F.col(_VERSIONE) == prossima).drop(_VERSIONE, COLONNA_SNAPSHOT)
    return righe, prossima
