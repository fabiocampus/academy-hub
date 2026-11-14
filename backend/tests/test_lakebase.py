"""Connessione a Lakebase e avvio dell'App su Databricks (ADR-0010).

Lakebase non gira in locale: i test usano il PostgreSQL di Testcontainers con la sua
password tolta dall'URL e restituita dal generatore di token, come farebbe l'SDK.
"""

from collections.abc import Callable, Iterator

import pytest
from databricks.sdk.service.postgres import DatabaseCredential
from sqlalchemy import Engine, create_engine, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from academy_hub.avvio import porta, prepara
from academy_hub.config import Impostazioni, impostazioni
from academy_hub.db import motore as motore_lakebase
from academy_hub.db.amministratore import assicura_amministratore
from academy_hub.db.migrazioni import aggiorna_schema, controlla_allineamento
from academy_hub.db.modelli import Persona, Team
from academy_hub.db.motore import crea_motore

ENDPOINT = "projects/academy-hub/branches/collaudo/endpoints/primary"


@pytest.fixture(autouse=True)
def impostazioni_rilette() -> Iterator[None]:
    impostazioni.cache_clear()
    yield
    impostazioni.cache_clear()


def senza_password(url: str) -> tuple[str, str]:
    completo = make_url(url)
    assert completo.password is not None
    return completo.set(password=None).render_as_string(hide_password=False), str(completo.password)


@pytest.mark.integrazione
def test_password_dal_token_a_ogni_nuova_connessione(
    nuovo_database: Callable[[str], str],
) -> None:
    url, password = senza_password(nuovo_database("academy_token"))
    richiesti: list[str] = []

    def genera(endpoint: str) -> str:
        richiesti.append(endpoint)
        return password

    config = Impostazioni(ambiente="collaudo", identita="databricks", lakebase_endpoint=ENDPOINT)
    motore = crea_motore(config, url, genera_token=genera, pool_size=1, max_overflow=0)
    try:
        for _ in range(2):  # la stessa connessione del pool: nessun token nuovo
            with motore.connect() as connessione:
                assert connessione.execute(text("SELECT 1")).scalar_one() == 1
        motore.dispose()
        with motore.connect() as connessione:  # connessione nuova: token nuovo
            connessione.execute(text("SELECT 1"))
    finally:
        motore.dispose()

    assert richiesti == [ENDPOINT, ENDPOINT]


def test_senza_endpoint_nessun_token() -> None:
    def genera(_endpoint: str) -> str:
        raise AssertionError("token chiesto senza endpoint Lakebase")

    motore = crea_motore(Impostazioni(), "postgresql+psycopg://nessuno@127.0.0.1:1/x", genera)
    # do_connect è un evento del dialetto, connect del pool: nessun listener in più
    # rispetto a un motore creato direttamente.
    semplice = create_engine("postgresql+psycopg://nessuno@127.0.0.1:1/x")
    assert not motore.dialect.dispatch.do_connect
    assert len(motore.pool.dispatch.connect) == len(semplice.pool.dispatch.connect)


def test_token_vuoto_rifiutato(monkeypatch: pytest.MonkeyPatch) -> None:
    class ClientFinto:
        class postgres:  # noqa: N801 - imita l'attributo dell'SDK
            @staticmethod
            def generate_database_credential(endpoint: str) -> DatabaseCredential:
                return DatabaseCredential(token="")

    monkeypatch.setattr(motore_lakebase, "_client", lambda: ClientFinto())
    with pytest.raises(RuntimeError, match="non ha restituito un token"):
        motore_lakebase.token_databricks(ENDPOINT)


def test_token_dall_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    chiesti: list[str] = []

    class ClientFinto:
        class postgres:  # noqa: N801 - imita l'attributo dell'SDK
            @staticmethod
            def generate_database_credential(endpoint: str) -> DatabaseCredential:
                chiesti.append(endpoint)
                return DatabaseCredential(token="tok")  # noqa: S106 - finto

    monkeypatch.setattr(motore_lakebase, "_client", lambda: ClientFinto())
    assert motore_lakebase.token_databricks(ENDPOINT) == "tok"
    assert chiesti == [ENDPOINT]


@pytest.mark.integrazione
def test_avvio_prepara_due_volte(
    nuovo_database: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il comando dell'App al primo avvio e al riavvio: schema, una sola persona admin."""
    url = nuovo_database("academy_avvio")
    monkeypatch.setenv("ACADEMY_DATABASE_URL", url)
    monkeypatch.setenv("ACADEMY_DATABASE_SCHEMA", "academy_prova")
    monkeypatch.setenv("ACADEMY_ADMIN_EMAIL", "admin@example.com")

    prepara()
    prepara()

    motore = crea_motore(impostazioni())
    try:
        with Session(motore) as sessione:
            persone = sessione.scalars(select(Persona)).all()
            assert [(p.email, p.ruoli) for p in persone] == [
                ("admin@example.com", ["dipendente", "admin_academy"])
            ]
    finally:
        motore.dispose()
    assert "persone" in inspect(create_engine(url)).get_table_names(schema="academy_prova")


@pytest.mark.integrazione
def test_migrazioni_nello_schema_dedicato(
    nuovo_database: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Su Lakebase il service principal non possiede public: tutto va nello schema suo."""
    url = nuovo_database("academy_schema")
    monkeypatch.setenv("ACADEMY_DATABASE_SCHEMA", "academy")

    aggiorna_schema(url)
    aggiorna_schema(url)  # al riavvio dell'App: nessun errore, nessuna modifica
    controlla_allineamento(url)

    ispettore = inspect(create_engine(url))
    assert "persone" in ispettore.get_table_names(schema="academy")
    assert "alembic_version" in ispettore.get_table_names(schema="academy")
    assert ispettore.get_table_names(schema="public") == []
    # L'app, con lo stesso schema, trova le tabelle senza qualificarle.
    motore = crea_motore(impostazioni(), url)
    try:
        with motore.connect() as connessione:
            assert connessione.execute(text("SELECT count(*) FROM persone")).scalar_one() == 0
    finally:
        motore.dispose()


def test_schema_con_caratteri_non_ammessi_rifiutato() -> None:
    with pytest.raises(ValueError, match="database_schema"):
        Impostazioni(database_schema='academy"; DROP')


@pytest.mark.integrazione
def test_amministratore_creato_una_volta(db: Engine) -> None:
    assert assicura_amministratore(db, " Admin.Vera@Example.com ") is True
    assert assicura_amministratore(db, "admin.vera@example.com") is False

    with Session(db) as sessione:
        persona = sessione.scalars(select(Persona)).one()
        assert persona.email == "admin.vera@example.com"
        assert persona.ruoli == ["dipendente", "admin_academy"]
        assert sessione.get(Team, persona.team_id) is not None


@pytest.mark.integrazione
def test_amministratore_esistente_non_toccato(db: Engine) -> None:
    """Riavviare l'App non ridà ruoli tolti dall'applicazione."""
    assicura_amministratore(db, "admin@example.com")
    with Session(db) as sessione, sessione.begin():
        sessione.execute(update(Persona).values(ruoli=["dipendente"]))

    assert assicura_amministratore(db, "admin@example.com") is False
    with Session(db) as sessione:
        assert sessione.scalars(select(Persona.ruoli)).one() == ["dipendente"]


def test_amministratore_email_non_valida() -> None:
    motore = create_engine("postgresql+psycopg://nessuno@127.0.0.1:1/x")
    with pytest.raises(ValueError, match="email"):
        assicura_amministratore(motore, "senza-chiocciola")


@pytest.mark.parametrize(
    ("variabili", "attesa"),
    [
        ({}, 8000),
        ({"DATABRICKS_APP_PORT": "8001"}, 8001),
        ({"DATABRICKS_APP_PORT": "8001", "UVICORN_PORT": "9000"}, 9000),
    ],
)
def test_porta_dell_app(variabili: dict[str, str], attesa: int) -> None:
    assert porta(variabili) == attesa
