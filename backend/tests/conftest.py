"""Fixture condivise. I test `integrazione` usano un PostgreSQL reale (Testcontainers)."""

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

from academy_hub.db.migrazioni import aggiorna_schema

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def immagine_postgres() -> str:
    """La stessa immagine (tag@digest) del servizio `db` di docker compose."""
    trovata = re.search(r"^\s+image:\s*(postgres:\S+)\s*$", COMPOSE.read_text(), re.MULTILINE)
    assert trovata, "immagine postgres non trovata in docker-compose.yml"
    return trovata.group(1)


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(immagine_postgres(), driver="psycopg") as contenitore:
        yield contenitore


def crea_database(postgres: PostgresContainer, nome: str) -> str:
    """Crea un database vuoto nel contenitore e ne restituisce l'URL."""
    url = make_url(postgres.get_connection_url())
    amministrazione = create_engine(url, isolation_level="AUTOCOMMIT")
    with amministrazione.connect() as connessione:
        connessione.execute(text(f'DROP DATABASE IF EXISTS "{nome}"'))
        connessione.execute(text(f'CREATE DATABASE "{nome}"'))
    amministrazione.dispose()
    return url.set(database=nome).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def nuovo_database(postgres: PostgresContainer) -> Callable[[str], str]:
    return lambda nome: crea_database(postgres, nome)


@pytest.fixture(scope="session")
def motore(postgres: PostgresContainer) -> Iterator[Engine]:
    """Database con lo schema creato dalle migrazioni Alembic (non da create_all)."""
    url = crea_database(postgres, "academy_test")
    aggiorna_schema(url)
    motore = create_engine(url)
    yield motore
    motore.dispose()


@pytest.fixture
def db(motore: Engine) -> Iterator[Engine]:
    """Svuota le tabelle dopo ogni test: i test di concorrenza usano più connessioni."""
    yield motore
    with motore.begin() as connessione:
        tabelle = connessione.execute(
            text(
                "SELECT string_agg(format('%I', tablename), ', ') FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalar_one()
        connessione.execute(text(f"TRUNCATE {tabelle} RESTART IDENTITY CASCADE"))
