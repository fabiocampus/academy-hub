"""Comando dell'App su Databricks: ``python -m academy_hub.avvio`` (ADR-0010).

Databricks Apps esegue un solo comando: qui le migrazioni, la persona amministratrice
da `ACADEMY_ADMIN_EMAIL` e poi uvicorn. Le migrazioni girano con l'identità dell'App,
così il suo service principal possiede schema e tabelle su Lakebase.
"""

import logging
import os
import sys

import uvicorn

from academy_hub.config import impostazioni
from academy_hub.db.amministratore import assicura_amministratore
from academy_hub.db.migrazioni import aggiorna_schema
from academy_hub.db.motore import crea_motore

log = logging.getLogger("academy_hub.avvio")


def porta(ambiente: dict[str, str]) -> int:
    """`DATABRICKS_APP_PORT` è la porta che il proxy dell'App si aspetta."""
    return int(ambiente.get("UVICORN_PORT") or ambiente.get("DATABRICKS_APP_PORT") or "8000")


def prepara() -> None:
    config = impostazioni()
    aggiorna_schema()
    log.info("Schema aggiornato")
    if config.admin_email:
        motore = crea_motore(config)
        try:
            creata = assicura_amministratore(motore, config.admin_email)
        finally:
            motore.dispose()
        log.info("Persona amministratrice %s", "creata" if creata else "già presente")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    prepara()
    uvicorn.run(
        "academy_hub.main:app",
        host=os.environ.get("UVICORN_HOST", "0.0.0.0"),  # noqa: S104 - dietro il proxy dell'App
        port=porta(dict(os.environ)),
        proxy_headers=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
