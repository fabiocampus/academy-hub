"""Le migrazioni Alembic sono l'unico modo di cambiare lo schema."""

from collections.abc import Callable

import pytest
from sqlalchemy import create_engine, inspect

from academy_hub.db.migrazioni import (
    aggiorna_schema,
    controlla_allineamento,
    riporta_a_vuoto,
)

pytestmark = pytest.mark.integrazione

TABELLE = {"team", "persone", "corsi", "edizioni", "iscrizioni", "eventi_audit"}


def tabelle(url: str) -> set[str]:
    motore = create_engine(url)
    try:
        return set(inspect(motore).get_table_names()) - {"alembic_version"}
    finally:
        motore.dispose()


def test_upgrade_check_downgrade_upgrade(nuovo_database: Callable[[str], str]) -> None:
    url = nuovo_database("academy_migrazioni")

    aggiorna_schema(url)
    assert tabelle(url) == TABELLE
    # Nessuna differenza fra i modelli SQLAlchemy e lo schema prodotto dalle migrazioni.
    controlla_allineamento(url)

    riporta_a_vuoto(url)
    assert tabelle(url) == set()

    aggiorna_schema(url)
    assert tabelle(url) == TABELLE
