"""Tabella gold sintetica di un target (ADR-0011).

    uv run --project backend python scripts/unity_catalog.py dati-gold -t collaudo

Catalogo, schemi e grant li crea e gestisce Terraform (`infra/databricks`, ADR-0012).

`dati-gold`: la tabella `gold.iscrizioni_per_corso` per il report letto con l'identità
dell'utente, finché la pipeline della fase 11 non la calcola da Lakebase. Idempotente
(`CREATE OR REPLACE`), valori fissi e sintetici. Gira con l'identità del profilo della CLI.
"""

import argparse
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

CATALOGHI = {"collaudo": "academy_collaudo", "prod": "academy_prod"}
# Cercato per nome, come nel bundle: l'id è del workspace e non sta nel repository.
WAREHOUSE = "Serverless Starter Warehouse"

# Gli stessi corsi dei dati demo (academy_hub.db.demo); i numeri sono inventati.
SQL = """
CREATE OR REPLACE TABLE iscrizioni_per_corso
COMMENT 'Iscrizioni per corso (sintetiche, fino alla pipeline della fase 11)'
AS SELECT
  CAST(corso_id AS BIGINT) AS corso_id,
  CAST(titolo AS STRING) AS titolo,
  CAST(edizioni AS INT) AS edizioni,
  CAST(confermate AS INT) AS confermate,
  CAST(in_attesa AS INT) AS in_attesa
FROM VALUES
  -- Doppi apici: in Spark SQL '' non è un apice ma due stringhe concatenate.
  (1, "Python per l'analisi dei dati", 2, 18, 3),
  (2, 'SQL avanzato', 1, 9, 0)
AS t(corso_id, titolo, edizioni, confermate, in_attesa)
"""


def esegui(w: WorkspaceClient, warehouse: str, sql: str, **dove: str) -> bool:
    risposta = w.statement_execution.execute_statement(
        warehouse_id=warehouse, statement=sql, wait_timeout="50s", **dove
    )
    stato = risposta.status
    if stato is None or stato.state != StatementState.SUCCEEDED:
        errore = stato.error.message if stato and stato.error else stato
        print(f"Fallito: {errore}", file=sys.stderr)
        return False
    return True


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argomenti.add_argument("comando", choices=["dati-gold"])
    argomenti.add_argument("-t", "--target", choices=sorted(CATALOGHI), required=True)
    argomenti.add_argument("-p", "--profilo", default="academy")
    argomenti.add_argument("--warehouse", default=WAREHOUSE, help="nome del SQL warehouse")
    a = argomenti.parse_args()

    w = WorkspaceClient(profile=a.profilo)
    warehouse = next((x.id for x in w.warehouses.list() if x.name == a.warehouse), None)
    if warehouse is None:
        print(f"Nessun SQL warehouse di nome {a.warehouse!r}", file=sys.stderr)
        return 1
    catalogo = CATALOGHI[a.target]
    if not esegui(w, warehouse, SQL, catalog=catalogo, schema="gold"):
        return 1
    print(f"{catalogo}.gold.iscrizioni_per_corso pronta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
