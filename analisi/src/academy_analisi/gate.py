"""Gate di qualità del job `analisi`: verdetti dei file importati ed esito (ADR-0017).

Il task `controlli` guarda lo stato dei file calcolato dalla pipeline
(`qualita.file_importati`) e fissa un verdetto per ogni file nuovo in `qualita.verdetti`:
il verdetto non cambia più, anche se le anagrafiche o la data di oggi farebbero cambiare
la classificazione delle righe (un giorno futuro diventa passato, una persona viene
aggiunta). Se un file nuovo è respinto il task fallisce e il job non aggiorna il gold;
i file respinti restano comunque fuori dal gold anche nelle passate dopo.

Il task `registra_esito` gira sempre, anche dopo un errore, e scrive in `qualita.esiti`
come è andata la passata e perché.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.letture import leggi_o_vuota
from academy_analisi.snapshot import nome_tabella

FILE_IMPORTATI = "file_importati"
VERDETTI = "verdetti"
ESITI = "esiti"
SCHEMA_STATO = (
    "file STRING, tipo STRING, caricato_il TIMESTAMP, righe BIGINT, scartate BIGINT, "
    "bloccanti BIGINT, accettato BOOLEAN, motivo STRING"
)
SCHEMA_VERDETTI = (
    "file STRING, tipo STRING, accettato BOOLEAN, motivo STRING, righe BIGINT, "
    "scartate BIGINT, run_id BIGINT, valutato_il TIMESTAMP"
)
SCHEMA_ESITI = (
    "run_id BIGINT, registrato_il TIMESTAMP, esito STRING, motivo STRING, "
    "stato_controlli STRING, stato_gold STRING"
)


class Esito(StrEnum):
    AGGIORNATO = "aggiornato"
    BLOCCATO = "bloccato"
    ERRORE = "errore"


@dataclass(frozen=True)
class Respinto:
    file: str
    tipo: str
    motivo: str


def motivo_blocco(respinti: Sequence[Respinto]) -> str:
    """I file respinti, per tipo e nome (senza la cartella del volume), col loro motivo."""
    return "; ".join(f"{r.tipo} {r.file.rsplit('/', 1)[-1]}: {r.motivo}" for r in respinti)


class FileRespintiError(RuntimeError):
    """Un file nuovo è respinto: il task `controlli` fallisce e il gold non si aggiorna."""

    def __init__(self, respinti: Sequence[Respinto]) -> None:
        super().__init__(f"Gate di qualità: file respinti. {motivo_blocco(respinti)}")
        self.respinti = list(respinti)


def controlla(
    *,
    spark: SparkSession,
    stato: DataFrame,
    verdetti: DataFrame,
    scrivi: Callable[[DataFrame], None],
    run_id: int,
    istante: datetime,
) -> list[Respinto]:
    """Fissa il verdetto dei file nuovi e restituisce quelli respinti.

    Un file è nuovo se non ha ancora un verdetto per il suo tipo. I verdetti si scrivono
    tutti, anche quelli dei file respinti, prima che il gate blocchi.
    """
    nuovi = (
        stato.join(verdetti.select("file", "tipo"), ["file", "tipo"], "left_anti")
        .select(
            "file",
            "tipo",
            "accettato",
            "motivo",
            "righe",
            "scartate",
            F.lit(run_id).cast("bigint").alias("run_id"),
            F.lit(istante).alias("valutato_il"),
        )
        .collect()
    )
    if nuovi:
        # Dalle righe già calcolate: scrivere il risultato di un join che legge la stessa
        # tabella di destinazione la rileggerebbe a metà.
        scrivi(spark.createDataFrame(nuovi, SCHEMA_VERDETTI))
    return [Respinto(r.file, r.tipo, r.motivo or "") for r in nuovi if not r.accettato]


def esito_passata(
    respinti: Sequence[Respinto], stato_controlli: str, stato_gold: str
) -> tuple[Esito, str | None]:
    """Esito e motivo di una passata, dai file respinti e dallo stato dei due task.

    Gli stati sono quelli dei riferimenti dinamici del job (`success`, `failed`,
    `upstream_failed`, ...).
    """
    if stato_gold == "success":
        return Esito.AGGIORNATO, None
    if respinti:
        return Esito.BLOCCATO, motivo_blocco(respinti)
    return Esito.ERRORE, f"controlli {stato_controlli}, gold {stato_gold}"


def scrivi_in_aggiunta(nome: str) -> Callable[[DataFrame], None]:
    def scrivi(righe: DataFrame) -> None:
        righe.write.mode("append").saveAsTable(nome)

    return scrivi


def _argomenti(descrizione: str) -> argparse.ArgumentParser:
    argomenti = argparse.ArgumentParser(description=descrizione)
    argomenti.add_argument("--qualita", required=True, help="catalogo.schema della qualità")
    argomenti.add_argument("--run-id", required=True, type=int, help="id della run del job")
    return argomenti


def main_controlli(argv: Sequence[str] | None = None) -> int:
    a = _argomenti("Gate di qualità: verdetti dei file importati").parse_args(argv)
    verdetti = nome_tabella(a.qualita, VERDETTI)
    spark = SparkSession.builder.getOrCreate()
    respinti = controlla(
        spark=spark,
        stato=leggi_o_vuota(spark, nome_tabella(a.qualita, FILE_IMPORTATI), SCHEMA_STATO),
        verdetti=leggi_o_vuota(spark, verdetti, SCHEMA_VERDETTI),
        scrivi=scrivi_in_aggiunta(verdetti),
        run_id=a.run_id,
        istante=datetime.now(UTC),
    )
    if respinti:
        raise FileRespintiError(respinti)
    print("Gate di qualità: nessun file nuovo respinto")
    return 0


def main_esito(argv: Sequence[str] | None = None) -> int:
    argomenti = _argomenti("Esito della passata del job analisi")
    argomenti.add_argument("--controlli", required=True, help="stato del task controlli")
    argomenti.add_argument("--gold", required=True, help="stato del task gold")
    a = argomenti.parse_args(argv)
    spark = SparkSession.builder.getOrCreate()
    respinti = [
        Respinto(r.file, r.tipo, r.motivo or "")
        for r in leggi_o_vuota(spark, nome_tabella(a.qualita, VERDETTI), SCHEMA_VERDETTI)
        .where((F.col("run_id") == a.run_id) & ~F.col("accettato"))
        .orderBy("tipo", "file")
        .collect()
    ]
    esito, motivo = esito_passata(respinti, a.controlli, a.gold)
    riga = spark.createDataFrame(
        [(a.run_id, datetime.now(UTC), esito.value, motivo, a.controlli, a.gold)], SCHEMA_ESITI
    )
    scrivi_in_aggiunta(nome_tabella(a.qualita, ESITI))(riga)
    print(f"Esito della passata {a.run_id}: {esito.value}" + (f" ({motivo})" if motivo else ""))
    return 0
