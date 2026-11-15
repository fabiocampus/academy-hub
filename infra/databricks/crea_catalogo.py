"""Crea un catalogo Unity Catalog in SQL (Free Edition: l'API non può, ADR-0011).

Lo lancia Terraform (terraform_data.catalogo) con WAREHOUSE_ID nell'ambiente.
Usa la CLI di Databricks, con le stesse credenziali del provider: profilo
(DATABRICKS_CONFIG_PROFILE) dal PC, service principal nel workflow.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

NOME = re.compile(r"[a-z][a-z0-9_]*")


def esegui_sql(istruzione: str) -> bool:
    """Un'istruzione sul warehouse WAREHOUSE_ID; False (con il motivo su stderr) se fallisce."""
    cli = shutil.which("databricks")
    if cli is None:
        print("Serve la CLI di Databricks nel PATH", file=sys.stderr)
        return False
    richiesta = {
        "warehouse_id": os.environ["WAREHOUSE_ID"],
        "statement": istruzione,
        "wait_timeout": "50s",
        "on_wait_timeout": "CANCEL",
    }
    esito = subprocess.run(  # noqa: S603 - eseguibile risolto, istruzione con nomi validati
        [cli, "api", "post", "/api/2.0/sql/statements", "--json", json.dumps(richiesta)],
        capture_output=True,
        text=True,
        check=False,
        # Fuori dal repository: dentro, la CLI troverebbe databricks.yml e userebbe
        # la configurazione del bundle invece delle credenziali dell'ambiente.
        cwd=tempfile.gettempdir(),
    )
    if esito.returncode != 0:
        print(esito.stderr, file=sys.stderr)
        return False
    try:
        stato = json.loads(esito.stdout).get("status", {})
    except json.JSONDecodeError:
        print(f"Risposta inattesa della CLI: {esito.stdout[:200]!r}", file=sys.stderr)
        return False
    if stato.get("state") != "SUCCEEDED":
        print(f"{istruzione}: {stato}", file=sys.stderr)
        return False
    return True


def main() -> int:
    if len(sys.argv) != 2 or not NOME.fullmatch(sys.argv[1]):
        print("Uso: crea_catalogo.py <nome> (minuscole, cifre, _)", file=sys.stderr)
        return 2
    nome = sys.argv[1]
    # Il nome è validato sopra: niente da citare.
    if not esegui_sql(f"CREATE CATALOG IF NOT EXISTS {nome}"):
        return 1
    print(f"Catalogo {nome} pronto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
