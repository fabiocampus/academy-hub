"""Comando dell'App su Databricks: ``python -m academy_hub.avvio`` (ADR-0010).

Databricks Apps esegue un solo comando: qui le migrazioni, la persona amministratrice
da `ACADEMY_ADMIN_EMAIL`, i dati di prova se `ACADEMY_DATI_PROVA` (solo collaudo,
`db/dati_prova.py`) e poi uvicorn. Le migrazioni girano con l'identità dell'App,
così il suo service principal possiede schema e tabelle su Lakebase.
"""

import logging
import os
import sys

import uvicorn

from academy_hub.config import impostazioni
from academy_hub.db import dati_prova
from academy_hub.db.amministratore import assicura_amministratore
from academy_hub.db.migrazioni import aggiorna_schema
from academy_hub.db.motore import crea_motore
from academy_hub.osservabilita import configura_log

log = logging.getLogger("academy_hub.avvio")


def porta(ambiente: dict[str, str]) -> int:
    """`DATABRICKS_APP_PORT` è la porta che il proxy dell'App si aspetta."""
    return int(ambiente.get("UVICORN_PORT") or ambiente.get("DATABRICKS_APP_PORT") or "8000")


def prepara() -> None:
    config = impostazioni()
    aggiorna_schema()
    log.info("Schema aggiornato")
    if not (config.admin_email or config.dati_prova):
        return
    motore = crea_motore(config)
    try:
        if config.admin_email:
            creata = assicura_amministratore(motore, config.admin_email)
            log.info("Persona amministratrice %s", "creata" if creata else "già presente")
        if config.dati_prova:
            riepilogo = dati_prova.carica(motore)
            if riepilogo is None:
                log.info("Dati di prova già presenti")
            else:
                log.info("Dati di prova caricati: %s", riepilogo)
    finally:
        motore.dispose()


def main() -> int:
    configura_log(impostazioni().livello_log)
    prepara()
    uvicorn.run(
        "academy_hub.main:app",
        host=os.environ.get("UVICORN_HOST", "0.0.0.0"),  # noqa: S104 - dietro il proxy dell'App
        port=porta(dict(os.environ)),
        # L'App è raggiungibile solo dal proxy di Databricks Apps (verificato, ADR-0010),
        # che non è su 127.0.0.1: senza "*" uvicorn ignorerebbe X-Forwarded-For/-Proto.
        # Log già configurati in JSON; l'access log di uvicorn (con l'IP) è sostituito
        # dalla riga del middleware Correlazione.
        log_config=None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
