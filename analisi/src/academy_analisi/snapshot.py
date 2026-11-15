"""Snapshot delle tabelle di Lakebase in bronze, solo in aggiunta (ADR-0016).

Ogni passata del job legge le tabelle dal catalogo Unity Catalog che registra il
database di Lakebase (sola lettura) e aggiunge le righe a `bronze.<tabella>` con lo
stesso `_snapshot_il` per tutte: bronze conserva ogni fotografia, silver ne ricava lo
storico. Le tabelle sono lette una dopo l'altra, non in una transazione: fra due letture
l'App può scrivere (accettabile per report giornalieri).
"""

import argparse
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.tabelle import TABELLE, Tabella

COLONNA_SNAPSHOT = "_snapshot_il"

# I nomi finiscono in spark.read.table e saveAsTable: solo `catalogo.schema` semplici.
_SCHEMA = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")


def nome_tabella(schema: str, tabella: str) -> str:
    """`catalogo.schema` + tabella, con lo schema validato."""
    if not _SCHEMA.fullmatch(schema):
        raise ValueError(f"Atteso catalogo.schema (minuscole, cifre, _), non {schema!r}")
    return f"{schema}.{tabella}"


def snapshot(sorgente: DataFrame, tabella: Tabella, istante: datetime) -> DataFrame:
    """Le colonne dichiarate della tabella più l'istante dello scatto."""
    return sorgente.select(*tabella.colonne).withColumn(COLONNA_SNAPSHOT, F.lit(istante))


def scatta(
    *,
    leggi: Callable[[str], DataFrame],
    scrivi: Callable[[DataFrame, str], None],
    tabelle: Iterable[Tabella],
    sorgente: str,
    destinazione: str,
    istante: datetime,
) -> dict[str, int]:
    """Uno snapshot di ogni tabella da `sorgente` a `destinazione`; righe scritte per tabella."""
    contate: dict[str, int] = {}
    for tabella in tabelle:
        righe = snapshot(leggi(nome_tabella(sorgente, tabella.nome)), tabella, istante)
        scrivi(righe, nome_tabella(destinazione, tabella.nome))
        # Solo per il log. Il compute serverless non ha cache(): è una seconda lettura,
        # che può differire di qualche riga se l'App ha scritto nel frattempo.
        contate[tabella.nome] = righe.count()
    return contate


def scrivi_in_aggiunta(righe: DataFrame, nome: str) -> None:
    """Aggiunge a una tabella Delta, creandola la prima volta; colonne nuove accettate."""
    righe.write.mode("append").option("mergeSchema", "true").saveAsTable(nome)


def main(argv: Sequence[str] | None = None) -> int:
    argomenti = argparse.ArgumentParser(description="Snapshot di Lakebase in bronze")
    argomenti.add_argument("--sorgente", required=True, help="catalogo.schema di Lakebase in UC")
    argomenti.add_argument("--destinazione", required=True, help="catalogo.schema bronze")
    a = argomenti.parse_args(argv)
    # Prima di toccare Spark: nomi non validi fermano il job subito.
    for t in TABELLE:
        nome_tabella(a.sorgente, t.nome)
        nome_tabella(a.destinazione, t.nome)

    spark = SparkSession.builder.getOrCreate()
    # Al microsecondo, come la versione dello storico: due passate nello stesso secondo
    # restano due snapshot distinti.
    istante = datetime.now(UTC)
    contate = scatta(
        leggi=spark.read.table,
        scrivi=scrivi_in_aggiunta,
        tabelle=TABELLE,
        sorgente=a.sorgente,
        destinazione=a.destinazione,
        istante=istante,
    )
    for nome, righe in contate.items():
        print(f"{a.destinazione}.{nome}: {righe} righe (snapshot {istante.isoformat()})")
    return 0
