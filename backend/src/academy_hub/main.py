"""Punto d'ingresso ASGI: ``uvicorn academy_hub.main:app``.

Host e porta arrivano da ``UVICORN_HOST`` e ``UVICORN_PORT``, che Databricks Apps
imposta da sé e il Dockerfile fissa per l'ambiente locale.
"""

from fastapi import FastAPI

from academy_hub import __version__
from academy_hub.config import impostazioni


def crea_app() -> FastAPI:
    app = FastAPI(title="Academy Hub", version=__version__)

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"stato": "ok", "versione": __version__, "ambiente": impostazioni().ambiente}

    return app


app = crea_app()
