"""Report letti da Unity Catalog con l'identità dell'utente (on-behalf-of-user, ADR-0011).

Le due identità dell'App restano separate:

- il service principal dell'App legge e scrive Lakebase (iscrizioni, ADR-0010) e non ha
  permessi su Unity Catalog;
- i report si leggono con il token dell'utente collegato, che Databricks Apps passa in
  `X-Forwarded-Access-Token` quando l'App ha lo scope `sql` (`user_api_scopes`). Così
  decide Unity Catalog, con i permessi di quella persona, non l'App.

La query passa dalla Statement Execution API su un SQL warehouse. Niente client dell'SDK
per richiesta: costruirlo risolve la configurazione in rete (circa un secondo); basta una
POST con il token come Bearer.

È un adapter verso un sistema esterno, fuori dai livelli router → servizi → repository
(ADR-0011): non ha regole di business e l'autorizzazione la fa Unity Catalog. Ai client
arrivano messaggi generici; codici e classi d'errore di Databricks restano nel log, senza
il token.
"""

import http.cookiejar
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from academy_hub.config import Impostazioni
from academy_hub.dominio.errori import ReportNonAutorizzato, ReportNonDisponibile

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RigaIscrizioniPerCorso:
    corso_id: int
    titolo: str
    edizioni: int
    confermate: int
    in_attesa: int


@dataclass(frozen=True)
class ReportIscrizioniPerCorso:
    # Chi ha letto secondo Databricks (current_user()): mostra che la query è dell'utente.
    # None se la tabella è vuota.
    letto_come: str | None
    righe: list[RigaIscrizioniPerCorso]


class LettoreReport(Protocol):
    def iscrizioni_per_corso(self, token_utente: str | None) -> ReportIscrizioniPerCorso:
        """Il report con l'identità del token; errori come eccezioni di questo modulo."""
        ...


class NessunReport:
    """Ambiente senza warehouse (locale, test): i report non ci sono."""

    def iscrizioni_per_corso(self, token_utente: str | None) -> ReportIscrizioniPerCorso:
        raise ReportNonDisponibile("Report non configurati in questo ambiente")


Invia = Callable[[str, dict[str, Any]], tuple[int, dict[str, Any]]]
"""Manda il corpo alla Statement Execution API con il token come Bearer: (stato, JSON)."""

COLONNE = ("letto_come", "corso_id", "titolo", "edizioni", "confermate", "in_attesa")
# Catalogo e schema arrivano come parametri della richiesta, mai nel testo SQL.
SQL_ISCRIZIONI_PER_CORSO = (
    "SELECT current_user() AS letto_come, corso_id, titolo, edizioni, confermate, in_attesa "
    "FROM iscrizioni_per_corso ORDER BY titolo, corso_id LIMIT 1000"
)
_NEGATO = {"INSUFFICIENT_PERMISSIONS", "PERMISSION_DENIED"}
_CLASSE_ERRORE = re.compile(r"^\[([A-Z_]+)\]")


class ReportDatabricks:
    # La API attende al più 50 secondi; un warehouse serverless spento parte in pochi.
    ATTESA = "30s"

    def __init__(self, warehouse_id: str, catalogo: str, invia: Invia) -> None:
        self._warehouse_id = warehouse_id
        self._catalogo = catalogo
        self._invia = invia

    @classmethod
    def da_host(cls, host: str, warehouse_id: str, catalogo: str) -> "ReportDatabricks":
        return cls(warehouse_id, catalogo, invio_http(host))

    def iscrizioni_per_corso(self, token_utente: str | None) -> ReportIscrizioniPerCorso:
        if not token_utente:
            raise ReportNonDisponibile(
                "Manca il token dell'utente: l'App deve avere lo scope sql (user_api_scopes)"
            )
        stato, risposta = self._invia(
            token_utente,
            {
                "warehouse_id": self._warehouse_id,
                "catalog": self._catalogo,
                "schema": "gold",
                "statement": SQL_ISCRIZIONI_PER_CORSO,
                "wait_timeout": self.ATTESA,
                "on_wait_timeout": "CANCEL",
                "disposition": "INLINE",
                "format": "JSON_ARRAY",
            },
        )
        _verifica_http(stato, risposta)
        return _report(_dati(risposta))


def _verifica_http(stato: int, risposta: dict[str, Any]) -> None:
    if stato == 200:
        return
    log.warning("Statement Execution API: HTTP %s %s", stato, risposta.get("error_code"))
    if stato == 403:
        raise ReportNonAutorizzato("Databricks nega l'uso del warehouse con la tua identità")
    # 401 compreso: l'utente è autenticato presso l'App, è il token passato dal proxy a
    # essere rifiutato a valle. Un 401 dell'App farebbe rifare il login per niente.
    raise ReportNonDisponibile("Il warehouse non ha accettato la richiesta")


def _dati(risposta: dict[str, Any]) -> list[list[str | None]]:
    stato: dict[str, Any] = risposta.get("status") or {}
    match stato.get("state"):
        case "SUCCEEDED":
            pass
        case "FAILED":
            errore: dict[str, Any] = stato.get("error") or {}
            codice = str(errore.get("error_code", ""))
            trovata = _CLASSE_ERRORE.match(str(errore.get("message", "")))
            classe = trovata.group(1) if trovata else ""
            log.warning("Report fallito: %s %s", codice, classe)
            if codice in _NEGATO or classe in _NEGATO:
                raise ReportNonAutorizzato("Unity Catalog nega la lettura con la tua identità")
            raise ReportNonDisponibile("Query del report fallita")
        case altro:
            # PENDING o RUNNING dopo l'attesa (la API l'ha già annullata), CANCELED, CLOSED.
            log.warning("Report non completato: %s", altro)
            raise ReportNonDisponibile("Il warehouse non ha completato la query in tempo")
    manifesto: dict[str, Any] = risposta.get("manifest") or {}
    schema: dict[str, Any] = manifesto.get("schema") or {}
    descritte: list[dict[str, Any]] = schema.get("columns") or []
    colonne = tuple(str(c.get("name")) for c in descritte)
    if colonne != COLONNE:
        log.warning("Colonne inattese nel report: %s", colonne)
        raise ReportNonDisponibile("La tabella del report non ha le colonne attese")
    risultato: dict[str, Any] = risposta.get("result") or {}
    righe: list[list[str | None]] = risultato.get("data_array") or []
    return righe


def _report(righe: list[list[str | None]]) -> ReportIscrizioniPerCorso:
    try:
        return ReportIscrizioniPerCorso(
            letto_come=righe[0][0] if righe else None,
            righe=[
                RigaIscrizioniPerCorso(
                    corso_id=int(r[1] or 0),
                    titolo=r[2] or "",
                    edizioni=int(r[3] or 0),
                    confermate=int(r[4] or 0),
                    in_attesa=int(r[5] or 0),
                )
                for r in righe
            ],
        )
    except (ValueError, IndexError) as errore:
        log.warning("Valori inattesi nel report: %s", type(errore).__name__)
        raise ReportNonDisponibile("Valori inattesi nella tabella del report") from errore


class Sessione(Protocol):
    """Quanto serve di `requests.Session`; i test ne passano una finta."""

    def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> Any: ...


def sessione_senza_cookie() -> Sessione:
    """Sessione HTTP riusata (connessioni in pool), condivisa fra le richieste di tutti gli
    utenti: per questo non accetta cookie, che altrimenti passerebbero da un utente
    all'altro."""
    import requests  # import pigro: in locale non serve

    sessione = requests.Session()
    sessione.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
    return sessione


def invio_http(host: str, sessione: Sessione | None = None, timeout_s: float = 60) -> Invia:
    """POST con `requests` (dipendenza dell'SDK di Databricks)."""
    import requests

    base = host if host.startswith("https://") else f"https://{host}"
    url = f"{base.rstrip('/')}/api/2.0/sql/statements"
    client = sessione or sessione_senza_cookie()

    def invia(token: str, corpo: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            risposta = client.post(
                url, json=corpo, headers={"Authorization": f"Bearer {token}"}, timeout=timeout_s
            )
        except requests.RequestException as errore:
            # Solo il tipo: il messaggio non serve e così il token non può finirci.
            log.warning("Warehouse non raggiungibile: %s", type(errore).__name__)
            raise ReportNonDisponibile("Warehouse non raggiungibile") from errore
        try:
            dati: Any = risposta.json()
        except ValueError:
            dati = None
        stato = int(risposta.status_code)
        if not isinstance(dati, dict):
            return stato, {}
        return stato, cast(dict[str, Any], dati)

    return invia


def lettore_report(impostazioni: Impostazioni) -> LettoreReport:
    if (
        impostazioni.report_warehouse_id is None
        or impostazioni.report_catalogo is None
        or impostazioni.databricks_host is None
    ):
        return NessunReport()
    return ReportDatabricks.da_host(
        impostazioni.databricks_host,
        impostazioni.report_warehouse_id,
        impostazioni.report_catalogo,
    )
