"""Build statica del frontend servita dallo stesso processo dell'API (ADR-0001, ADR-0009 §13).

Databricks Apps esegue un solo processo: FastAPI serve l'API sotto `/api`, la build
di Vite (`frontend/dist`) e, per ogni altra GET, `index.html`, che lascia la rotta al
router del client. Le rotte qui restano fuori dal contratto OpenAPI.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from academy_hub.api import PREFISSO

# Vite mette l'hash del contenuto nel nome degli asset: un file non cambia mai.
CACHE_ASSET = "public, max-age=31536000, immutable"
# index.html invece cambia a ogni build e punta agli asset nuovi: va sempre riconvalidato.
CACHE_INDICE = "no-cache"


class _AssetImmutabili(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        risposta = await super().get_response(path, scope)
        if risposta.status_code == 200:
            risposta.headers["Cache-Control"] = CACHE_ASSET
        return risposta


def monta_frontend(app: FastAPI, cartella: Path) -> None:
    """Da chiamare dopo aver registrato tutte le rotte: il fallback le copre tutte."""
    radice = cartella.resolve()
    indice = radice / "index.html"
    if not indice.is_file():
        raise RuntimeError(f"build del frontend senza index.html in {radice}")
    # check_dir=False: una build senza asset è strana ma non un motivo per non partire.
    app.mount("/assets", _AssetImmutabili(directory=radice / "assets", check_dir=False))
    api = PREFISSO.split("/")[1]  # "api": tutto quello che sta sotto resta JSON

    @app.get("/{percorso:path}", include_in_schema=False)
    def spa(percorso: str) -> FileResponse:  # pyright: ignore[reportUnusedFunction]
        if percorso == api or percorso.startswith(f"{api}/"):
            raise HTTPException(404)
        file = (radice / percorso).resolve()
        if file != indice and file.is_relative_to(radice) and file.is_file():
            return FileResponse(file)
        return FileResponse(indice, headers={"Cache-Control": CACHE_INDICE})
