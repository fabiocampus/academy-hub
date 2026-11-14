"""Punto d'ingresso ASGI: ``uvicorn academy_hub.main:app``.

Host e porta arrivano da ``UVICORN_HOST`` e ``UVICORN_PORT``, che Databricks Apps
imposta da sé e il Dockerfile fissa per l'ambiente locale.
"""

from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from academy_hub import __version__
from academy_hub.api import PREFISSO, VERSIONE_API
from academy_hub.api.errori import registra_gestori
from academy_hub.api.identita import ProviderIdentita, provider
from academy_hub.api.rotte import catalogo, corsi, edizioni, iscrizioni, profilo
from academy_hub.config import impostazioni
from academy_hub.frontend import monta_frontend


def crea_app(
    motore: Engine | None = None,
    identita: ProviderIdentita | None = None,
    frontend: Path | None = None,
) -> FastAPI:
    """App FastAPI. `motore`, `identita` e `frontend` servono ai test; altrimenti nascono
    dalla configurazione. Con una build del frontend l'app serve anche la SPA.

    `create_engine` non apre connessioni: l'app parte (e genera l'OpenAPI) anche
    senza database.
    """
    app = FastAPI(
        title="Academy Hub",
        version=VERSIONE_API,
        description="Iscrizioni ai corsi dell'Academy. Errori in formato RFC 9457.",
    )
    app.state.motore = motore or create_engine(impostazioni().database_url, pool_pre_ping=True)
    app.state.identita = identita or provider(impostazioni())
    registra_gestori(app)
    for router in (
        catalogo.router,
        corsi.router,
        edizioni.router,
        iscrizioni.router,
        iscrizioni.richieste,
        profilo.router,
    ):
        app.include_router(router, prefix=PREFISSO)

    @app.get("/health", tags=["sistema"], operation_id="health")
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"stato": "ok", "versione": __version__, "ambiente": impostazioni().ambiente}

    cartella = frontend or impostazioni().frontend_dir
    if cartella is not None:
        monta_frontend(app, cartella)
    return app


app = crea_app()
