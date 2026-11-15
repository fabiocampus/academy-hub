"""Log strutturati: una riga JSON per evento, con l'id di correlazione della richiesta.

Regola (fase 12): nei log niente dati personali né segreti. Per questo
- l'eccezione si registra con classe e stack, senza il messaggio, che può contenere
  parametri SQL o valori arrivati dall'utente (per esempio un'email in un IntegrityError);
- la riga di ogni richiesta porta il modello della rotta (``/api/v1/iscrizioni/{id}``), non
  la query string né gli header;
- niente access log di uvicorn, che registra anche l'IP del client.
"""

import json
import logging
import logging.config
import re
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-Id"
_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

id_richiesta: ContextVar[str | None] = ContextVar("id_richiesta", default=None)

log = logging.getLogger("academy_hub.richieste")


class FormatoJson(logging.Formatter):
    """Campi fissi più quelli passati con ``extra={"campi": {...}}``."""

    def format(self, record: logging.LogRecord) -> str:
        riga: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "livello": record.levelname,
            "logger": record.name,
            "messaggio": record.getMessage(),
        }
        richiesta = id_richiesta.get()
        if richiesta is not None:
            riga["request_id"] = richiesta
        campi = getattr(record, "campi", None)
        if isinstance(campi, dict):
            riga.update(campi)  # pyright: ignore[reportUnknownArgumentType]
        if record.exc_info and record.exc_info[0] is not None:
            classe, _, tb = record.exc_info
            riga["eccezione"] = classe.__qualname__
            riga["stack"] = "".join(traceback.format_tb(tb))
        return json.dumps(riga, ensure_ascii=False, default=str)


def configura_log(livello: str = "INFO") -> None:
    """Tutti i log (anche uvicorn) in JSON su stderr. Idempotente."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": FormatoJson}},
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stderr",
                }
            },
            "root": {"level": livello, "handlers": ["stderr"]},
            "loggers": {
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                # Sostituito dalla riga di academy_hub.richieste, senza IP.
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )


def nuovo_id(valore: str | None) -> str:
    """L'id ricevuto se ha una forma sicura da scrivere nei log, altrimenti uno nuovo."""
    if valore is not None and _VALIDO.fullmatch(valore):
        return valore
    return uuid.uuid4().hex


class Correlazione:
    """Middleware ASGI: legge o genera ``X-Request-Id``, lo restituisce e registra una
    riga per richiesta (metodo, rotta, stato, durata)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ricevuto = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), None
        )
        rid = nuovo_id(ricevuto)
        # Non si azzera alla fine: ogni richiesta gira nel suo contesto, e il gestore degli
        # errori 500 (fuori da questo middleware) deve ancora vederlo.
        id_richiesta.set(rid)
        stato = 500
        inizio = time.perf_counter()

        async def invia(messaggio: Message) -> None:
            nonlocal stato
            if messaggio["type"] == "http.response.start":
                stato = messaggio["status"]
                messaggio["headers"] = [
                    *messaggio.get("headers", []),
                    (HEADER.lower().encode(), rid.encode()),
                ]
            await send(messaggio)

        try:
            await self.app(scope, receive, invia)
        finally:
            rotta = scope.get("route")
            percorso = getattr(rotta, "path", None) or "(nessuna rotta)"
            log.info(
                "richiesta",
                extra={
                    "campi": {
                        "metodo": scope["method"],
                        "rotta": percorso,
                        "stato": stato,
                        "durata_ms": round((time.perf_counter() - inizio) * 1000, 1),
                    }
                },
            )
