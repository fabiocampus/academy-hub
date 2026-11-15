"""Rende visibili a Unity Catalog gli schemi di un catalogo di Lakebase (ADR-0016).

Un catalogo appena registrato (databricks_postgres_catalog) non mostra i suoi schemi
all'API di Unity Catalog finché una query non li legge: prima, un grant su uno schema
risponde "does not exist". Un `SHOW SCHEMAS` dal warehouse li carica. Lo lancia
Terraform (terraform_data.schemi_oltp) con WAREHOUSE_ID nell'ambiente.
"""

import sys

from crea_catalogo import NOME, esegui_sql


def main() -> int:
    if len(sys.argv) != 2 or not NOME.fullmatch(sys.argv[1]):
        print("Uso: carica_schemi.py <catalogo> (minuscole, cifre, _)", file=sys.stderr)
        return 2
    catalogo = sys.argv[1]
    if not esegui_sql(f"SHOW SCHEMAS IN {catalogo}"):
        return 1
    print(f"Schemi di {catalogo} visibili")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
