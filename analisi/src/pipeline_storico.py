"""Pipeline Lakeflow `storico`: silver con SCD di tipo 2 dagli snapshot di bronze (ADR-0016).

Catalogo e schema di difetto (silver) li dà il bundle; bronze si nomina con lo schema.
`create_auto_cdc_from_snapshot_flow` esiste solo nel runtime di Databricks, non in
pyspark open source: la logica sta in academy_analisi.storico, testata con Spark locale.
La radice della pipeline (root_path nel bundle) è questa cartella, in sys.path.
"""
# pyright: reportAttributeAccessIssue=false

from collections.abc import Callable

from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

from academy_analisi.snapshot import TABELLA_SCATTI
from academy_analisi.storico import leggi_scatti, prossimo_snapshot
from academy_analisi.tabelle import TABELLE, Tabella

Sorgente = Callable[[int | None], tuple[DataFrame, int] | None]


def _sorgente(tabella: Tabella) -> Sorgente:
    def prossimo(ultima: int | None) -> tuple[DataFrame, int] | None:
        spark = SparkSession.active()
        return prossimo_snapshot(
            spark.read.table(f"bronze.{tabella.nome}"),
            leggi_scatti(spark, f"bronze.{TABELLA_SCATTI}"),
            ultima,
        )

    return prossimo


for _tabella in TABELLE:
    dp.create_streaming_table(
        name=_tabella.nome,
        comment=f"Storico di {_tabella.nome} da Lakebase (SCD 2: __START_AT, __END_AT)",
    )
    dp.create_auto_cdc_from_snapshot_flow(
        target=_tabella.nome,
        source=_sorgente(_tabella),
        keys=list(_tabella.chiave),
        stored_as_scd_type=2,
    )
