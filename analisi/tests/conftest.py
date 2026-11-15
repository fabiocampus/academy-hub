"""Spark locale per i test delle trasformazioni (serve Java 17+ nel PATH o in JAVA_HOME)."""

import os
import sys
from collections.abc import Iterator

import pytest
from pyspark.sql import SparkSession

# Su Windows i worker Python di Spark devono usare lo stesso interprete dei test.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
# Lo Spark del pacchetto pyspark, non un'installazione della macchina di un'altra versione
# (jar diversi: "'JavaPackage' object is not callable").
os.environ.pop("SPARK_HOME", None)


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    sessione = (
        SparkSession.builder.master("local[1]")
        .appName("academy-analisi-test")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield sessione
    sessione.stop()
