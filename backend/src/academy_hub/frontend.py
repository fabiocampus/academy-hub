"""Build statica del frontend servita dallo stesso processo dell'API (ADR-0001, ADR-0009 §14).

Databricks Apps esegue un solo processo: FastAPI serve l'API sotto `/api`, la build
di Vite (`frontend/dist`) e, per ogni altra GET, `index.html`, che lascia la rotta al
router del client. Ogni file `.html` della build (anche la pagina pubblica
`benvenuto.html`) esce con le intestazioni di `index.html`. Le rotte qui restano fuori
dal contratto OpenAPI.
"""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.convertors import Convertor, register_url_convertor
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from academy_hub.api import PREFISSO

# Vite mette l'hash del contenuto nel nome degli asset: un file non cambia mai.
CACHE_ASSET = "public, max-age=31536000, immutable"
# index.html invece cambia a ogni build e punta agli asset nuovi: va sempre riconvalidato.
CACHE_INDICE = "no-cache"
_API = PREFISSO.split("/")[1]  # "api"


class _FuoriDallApi(Convertor[str]):
    """Un percorso che non sta sotto `/api`.

    Il fallback non deve neanche combaciare con l'API: altrimenti `POST /api/x`
    sconosciuto diventerebbe 405 (il percorso c'è, il metodo no) invece di 404.
    """

    regex = rf"(?!{_API}(?:/|$)).*"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("fuori_api", _FuoriDallApi())


def _sicurezza(origini_esterne: list[str]) -> dict[str, str]:
    """Intestazioni dell'HTML: il token sta in sessionStorage, un XSS varrebbe una sessione.

    Mantine scrive stili inline (attributi `style` e tag `<style>`), quindi `style-src`
    ammette `'unsafe-inline'`; gli script restano solo quelli della build (threat model).
    """
    esterne = "".join(f" {o}" for o in origini_esterne)
    cornici = esterne or " 'none'"  # rinnovo silenzioso del token in un iframe del provider
    csp = "; ".join(
        (
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src 'self'{esterne}",
            f"frame-src{cornici}",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )
    )
    return {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }


class _AssetImmutabili(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if "\x00" in path:
            raise HTTPException(404)
        risposta = await super().get_response(path, scope)
        if risposta.status_code == 200:
            risposta.headers["Cache-Control"] = CACHE_ASSET
            risposta.headers["X-Content-Type-Options"] = "nosniff"
        return risposta


def origine(url: str) -> str:
    parti = urlsplit(url)
    return f"{parti.scheme}://{parti.netloc}"


def monta_frontend(app: FastAPI, cartella: Path, origini_esterne: list[str]) -> None:
    """Da chiamare dopo aver registrato tutte le rotte: il fallback le copre tutte.

    `origini_esterne`: con cui il browser parla oltre all'app (l'emittente OIDC).
    """
    radice = cartella.resolve()
    indice = radice / "index.html"
    if not indice.is_file():
        raise RuntimeError(f"build del frontend senza index.html in {radice}")
    # check_dir=False: una build senza asset è strana ma non un motivo per non partire.
    app.mount("/assets", _AssetImmutabili(directory=radice / "assets", check_dir=False))
    intestazioni_indice = {"Cache-Control": CACHE_INDICE, **_sicurezza(origini_esterne)}

    @app.api_route("/{percorso:fuori_api}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(percorso: str) -> FileResponse:  # pyright: ignore[reportUnusedFunction]
        if "\x00" in percorso:
            raise HTTPException(404)
        file = (radice / percorso).resolve()
        if file != indice and file.is_relative_to(radice) and file.is_file():
            # Un altro HTML (la pagina pubblica benvenuto.html) è una pagina come index:
            # stessa CSP e niente cache, perché anche lui punta a file che cambiano.
            if file.suffix == ".html":
                return FileResponse(file, headers=intestazioni_indice)
            return FileResponse(file, headers={"X-Content-Type-Options": "nosniff"})
        return FileResponse(indice, headers=intestazioni_indice)
