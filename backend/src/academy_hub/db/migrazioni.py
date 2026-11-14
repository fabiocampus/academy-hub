"""Migrazioni Alembic usabili da codice, dai test e dal container.

`python -m academy_hub.db.migrazioni` porta lo schema all'ultima versione usando
`ACADEMY_DATABASE_URL`: è il comando del servizio `migrazioni` di docker compose.
"""

import logging
from importlib.resources import files

from alembic import command
from alembic.config import Config


def configurazione(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("academy_hub.db") / "schema"))
    if url is not None:
        cfg.attributes["url"] = url
    return cfg


def aggiorna_schema(url: str | None = None) -> None:
    command.upgrade(configurazione(url), "head")


def riporta_a_vuoto(url: str | None = None) -> None:
    command.downgrade(configurazione(url), "base")


def controlla_allineamento(url: str | None = None) -> None:
    """Fallisce se i modelli differiscono dallo schema prodotto dalle migrazioni."""
    command.check(configurazione(url))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    aggiorna_schema()
