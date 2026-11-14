"""Errori in formato RFC 9457 (`application/problem+json`).

`type` è un riferimento relativo `/problemi/<tipo>`, con `<tipo>` preso dall'errore di
dominio: è stabile e i client possono confrontarlo. Il codice HTTP dipende solo dalla
classe base dell'errore (`STATO_HTTP`).
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException

from academy_hub.dominio.errori import (
    AzioneNonConsentita,
    Conflitto,
    DatiNonValidi,
    ErroreDominio,
    NonAutenticato,
    NonTrovato,
    VersioneNonCorrispondente,
)

TIPO_MEDIA = "application/problem+json"

log = logging.getLogger(__name__)

STATO_HTTP: dict[type[ErroreDominio], int] = {
    NonAutenticato: 401,
    AzioneNonConsentita: 403,
    NonTrovato: 404,
    Conflitto: 409,
    VersioneNonCorrispondente: 412,
    DatiNonValidi: 422,
}


class PrecondizioneRichiesta(ErroreDominio):
    """Modifica senza `If-Match`: il client deve dire quale versione ha letto."""

    tipo = "precondizione-richiesta"
    titolo = "Header If-Match obbligatorio"


STATO_HTTP[PrecondizioneRichiesta] = 428


class EtagNonValido(ErroreDominio):
    """`If-Match` malformato: non corrisponde a nessuna versione, quindi 412 (RFC 9110)."""

    tipo = VersioneNonCorrispondente.tipo
    titolo = VersioneNonCorrispondente.titolo

    def __init__(self, valore: str) -> None:
        self.valore = valore
        super().__init__(f"If-Match {valore!r} non è un ETag di questa API")


STATO_HTTP[EtagNonValido] = 412


class ErroreCampo(BaseModel):
    campo: str
    messaggio: str


class Problema(BaseModel):
    """Corpo degli errori (RFC 9457), con l'estensione `errori` per i dati non validi."""

    type: str = Field(examples=["/problemi/iscrizione-duplicata"])
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errori: list[ErroreCampo] | None = None


def risposte(*stati: int) -> dict[int | str, dict[str, Any]]:
    """Voci `responses` dell'OpenAPI per gli errori che una rotta può restituire.

    `model` registra lo schema `Problema`; `contratto_problem_json` lo sposta poi sotto
    il tipo di media giusto.
    """
    return {stato: {"model": Problema, "description": HTTPStatus(stato).phrase} for stato in stati}


def contratto_problem_json(app: FastAPI) -> None:
    """Nel contratto ogni risposta 4xx/5xx è `application/problem+json` con schema `Problema`.

    FastAPI documenta gli errori come `application/json` e aggiunge da sé un 422 con lo
    schema `HTTPValidationError`, che questa API non restituisce mai.
    """
    genera = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = genera()
        problema = {"schema": {"$ref": "#/components/schemas/Problema"}}
        for operazioni in schema.get("paths", {}).values():
            for operazione in operazioni.values():
                for stato, risposta in operazione.get("responses", {}).items():
                    if stato.startswith(("4", "5")):
                        risposta["content"] = {TIPO_MEDIA: problema}
        componenti = schema.get("components", {}).get("schemas", {})
        for nome in ("HTTPValidationError", "ValidationError"):
            componenti.pop(nome, None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi


def stato_http(errore: ErroreDominio) -> int:
    for classe in type(errore).__mro__:
        if classe in STATO_HTTP:
            return STATO_HTTP[classe]  # type: ignore[index]
    return 500


def problema(
    richiesta: Request,
    stato: int,
    tipo: str,
    titolo: str,
    dettaglio: str | None = None,
    errori: list[ErroreCampo] | None = None,
) -> JSONResponse:
    corpo = Problema(
        type=tipo,
        title=titolo,
        status=stato,
        detail=dettaglio,
        instance=richiesta.url.path,
        errori=errori,
    )
    return JSONResponse(
        corpo.model_dump(exclude_none=True), status_code=stato, media_type=TIPO_MEDIA
    )


def _campo(posizione: tuple[int | str, ...]) -> str:
    # ("body", "durata_ore") -> "durata_ore"; ("query", "limite") -> "limite"
    return ".".join(str(p) for p in posizione[1:]) or str(posizione[0])


async def _errore_dominio(richiesta: Request, errore: Exception) -> JSONResponse:
    if not isinstance(errore, ErroreDominio):
        raise errore
    errori = (
        [ErroreCampo(campo=errore.campo, messaggio=errore.messaggio)]
        if isinstance(errore, DatiNonValidi)
        else None
    )
    return problema(
        richiesta,
        stato_http(errore),
        f"/problemi/{errore.tipo}",
        errore.titolo,
        str(errore) or None,
        errori,
    )


async def _validazione(richiesta: Request, errore: Exception) -> JSONResponse:
    if not isinstance(errore, RequestValidationError):
        raise errore
    errori = [
        ErroreCampo(campo=_campo(tuple(e["loc"])), messaggio=str(e["msg"])) for e in errore.errors()
    ]
    return problema(
        richiesta, 422, f"/problemi/{DatiNonValidi.tipo}", DatiNonValidi.titolo, None, errori
    )


async def _http(richiesta: Request, errore: Exception) -> JSONResponse:
    if not isinstance(errore, HTTPException):
        raise errore
    titolo = HTTPStatus(errore.status_code).phrase
    dettaglio = errore.detail if errore.detail != titolo else None
    risposta = problema(richiesta, errore.status_code, "about:blank", titolo, dettaglio)
    if errore.headers:
        risposta.headers.update(errore.headers)
    return risposta


async def _versione_superata(richiesta: Request, errore: Exception) -> JSONResponse:
    # Ultima difesa: version_id_col ha trovato la riga già cambiata al momento dell'UPDATE.
    return problema(
        richiesta,
        412,
        f"/problemi/{VersioneNonCorrispondente.tipo}",
        VersioneNonCorrispondente.titolo,
        "La risorsa è cambiata durante la modifica: rileggila",
    )


async def _imprevisto(richiesta: Request, errore: Exception) -> JSONResponse:
    # Il dettaglio resta nel log: nel corpo potrebbe esporre dati interni.
    # Una riga sola: il traceback lo registra il server, a cui Starlette rilancia l'errore.
    log.error("Errore imprevisto su %s %s: %r", richiesta.method, richiesta.url.path, errore)
    return problema(richiesta, 500, "about:blank", HTTPStatus(500).phrase)


def registra_gestori(app: FastAPI) -> None:
    contratto_problem_json(app)
    app.add_exception_handler(ErroreDominio, _errore_dominio)
    app.add_exception_handler(RequestValidationError, _validazione)
    app.add_exception_handler(HTTPException, _http)
    app.add_exception_handler(StaleDataError, _versione_superata)
    app.add_exception_handler(Exception, _imprevisto)
