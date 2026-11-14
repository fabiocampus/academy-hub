"""Punto d'ingresso ASGI: ``uvicorn academy_hub.main:app``.

Host e porta arrivano da ``UVICORN_HOST`` e ``UVICORN_PORT``, che Databricks Apps
imposta da sé e il Dockerfile fissa per l'ambiente locale.
"""

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from academy_hub import __version__
from academy_hub.api import PREFISSO, VERSIONE_API
from academy_hub.api.errori import registra_gestori
from academy_hub.api.rotte import catalogo, corsi, edizioni, iscrizioni
from academy_hub.config import impostazioni


def crea_app(motore: Engine | None = None) -> FastAPI:
    """App FastAPI. `motore` serve ai test; altrimenti nasce da `ACADEMY_DATABASE_URL`.

    `create_engine` non apre connessioni: l'app parte (e genera l'OpenAPI) anche
    senza database.
    """
    app = FastAPI(
        title="Academy Hub",
        version=VERSIONE_API,
        description="Iscrizioni ai corsi dell'Academy. Errori in formato RFC 9457.",
    )
    app.state.motore = motore or create_engine(impostazioni().database_url, pool_pre_ping=True)
    registra_gestori(app)
    for router in (
        catalogo.router,
        corsi.router,
        edizioni.router,
        iscrizioni.router,
        iscrizioni.richieste,
    ):
        app.include_router(router, prefix=PREFISSO)

    @app.get("/health", tags=["sistema"], operation_id="health")
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"stato": "ok", "versione": __version__, "ambiente": impostazioni().ambiente}

    return app


app = crea_app()
