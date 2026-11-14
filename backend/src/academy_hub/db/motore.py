"""Motore SQLAlchemy unico per app, job, migrazioni e dati iniziali (ADR-0010).

In locale l'URL contiene tutto. Su Databricks l'App riceve dalla risorsa `postgres`
le variabili standard di libpq (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`):
l'URL resta `postgresql+psycopg://` e libpq le legge da sé. Manca solo la password: è un
token OAuth che scade dopo un'ora, quindi si genera a ogni nuova connessione del pool
invece di stare nella configurazione.
"""

from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, create_engine, event

from academy_hub.config import Impostazioni

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

GeneraToken = Callable[[str], str]
"""Dall'endpoint Lakebase al token da usare come password."""


@cache
def _client() -> "WorkspaceClient":
    """Un client per processo: risolvere l'autenticazione a ogni connessione costa."""
    from databricks.sdk import WorkspaceClient  # import pigro: in locale non serve

    return WorkspaceClient()


def token_databricks(endpoint: str) -> str:
    """Token dell'identità corrente (service principal dell'App, o l'utente della CLI)."""
    credenziale = _client().postgres.generate_database_credential(endpoint=endpoint)
    if not credenziale.token:
        raise RuntimeError(f"Lakebase non ha restituito un token per {endpoint}")
    return credenziale.token


def crea_motore(
    config: Impostazioni,
    url: str | None = None,
    genera_token: GeneraToken = token_databricks,
    **opzioni: Any,
) -> Engine:
    """`url` sostituisce `config.database_url` (test, migrazioni su un altro database)."""
    motore = create_engine(url or config.database_url, **opzioni)
    endpoint = config.lakebase_endpoint
    schema = config.database_schema

    if endpoint is not None:

        @event.listens_for(motore, "do_connect")
        def _password(  # pyright: ignore[reportUnusedFunction]
            _dialetto: Any, _record: Any, _argomenti: Any, parametri: dict[str, Any]
        ) -> None:
            parametri["password"] = genera_token(endpoint)

    if schema is not None:
        # SET e non l'opzione di avvio `-c search_path`: i pooler come PgBouncer la rifiutano.
        @event.listens_for(motore, "connect")
        def _schema(  # pyright: ignore[reportUnusedFunction]
            connessione: Any, _record: Any
        ) -> None:
            with connessione.cursor() as cursore:
                cursore.execute(f'SET search_path TO "{schema}"')
            connessione.commit()

    return motore
