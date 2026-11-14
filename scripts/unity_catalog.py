"""Unity Catalog di un target (ADR-0011): catalogo da creare e tabella gold sintetica.

    # 1. una volta: crea il catalogo
    uv run --project backend python scripts/unity_catalog.py catalogo -t collaudo
    # 2. una volta: il bundle prende in carico il catalogo
    databricks bundle deployment bind academy academy_collaudo -t collaudo -p academy
    # 3. schemi e grant
    databricks bundle deploy -t collaudo -p academy
    # 4. tabella gold
    uv run --project backend python scripts/unity_catalog.py dati-gold -t collaudo

`catalogo`: Free Edition non ha uno storage root del metastore, quindi l'API (e il bundle)
non crea cataloghi; `CREATE CATALOG` in SQL sì, sul Default Storage. Il bundle poi prende
in carico il catalogo con `bind` e ne gestisce commento, grant e schemi.

`dati-gold`: la tabella `gold.iscrizioni_per_corso` per il report letto con l'identità
dell'utente, finché la pipeline della fase 11 non la calcola da Lakebase. Idempotente
(`CREATE OR REPLACE`), valori fissi e sintetici.

Gira con l'identità del profilo della CLI, che resta proprietaria del catalogo.
"""

import argparse
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

CATALOGHI = {"collaudo": "academy_collaudo", "prod": "academy_prod"}
WAREHOUSE = "9f8eb48fc8353aa1"

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
    argomenti.add_argument("comando", choices=["catalogo", "dati-gold"])
    argomenti.add_argument("-t", "--target", choices=sorted(CATALOGHI), required=True)
    argomenti.add_argument("-p", "--profilo", default="academy")
    argomenti.add_argument("--warehouse", default=WAREHOUSE)
    a = argomenti.parse_args()

    w = WorkspaceClient(profile=a.profilo)
    catalogo = CATALOGHI[a.target]
    if a.comando == "catalogo":
        # Il nome viene da CATALOGHI, non da chi lancia lo script.
        if not esegui(w, a.warehouse, f"CREATE CATALOG IF NOT EXISTS {catalogo}"):
            return 1
        print(f"{catalogo} pronto: ora `bundle deployment bind academy {catalogo}`")
        return 0
    if not esegui(w, a.warehouse, SQL, catalog=catalogo, schema="gold"):
        return 1
    print(f"{catalogo}.gold.iscrizioni_per_corso pronta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
