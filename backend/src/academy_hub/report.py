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
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from academy_hub.config import Impostazioni
from academy_hub.dominio.errori import AzioneNonConsentita, ErroreDominio, NonAutenticato

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


class ReportNonAutorizzato(AzioneNonConsentita):
    """Unity Catalog (o il warehouse) nega la lettura all'utente collegato."""

    tipo = "report-non-autorizzato"
    titolo = "Non hai i permessi per leggere questo report"


class ReportNonDisponibile(ErroreDominio):
    """Il report non si può leggere ora: configurazione, warehouse o tabella mancanti."""

    tipo = "report-non-disponibile"
    titolo = "Report non disponibile"


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
    if stato == 401:
        raise NonAutenticato("Token dell'utente rifiutato da Databricks")
    if stato == 403:
        raise ReportNonAutorizzato("Databricks nega l'uso del warehouse con la tua identità")
    raise ReportNonDisponibile(f"Il warehouse ha risposto con HTTP {stato}")


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
                raise ReportNonAutorizzato(f"Unity Catalog nega la lettura: {classe or codice}")
            raise ReportNonDisponibile(f"Query del report fallita: {classe or codice}")
        case altro:
            # PENDING o RUNNING dopo l'attesa (la API l'ha già annullata), CANCELED, CLOSED.
            raise ReportNonDisponibile(f"Il warehouse non ha completato la query ({altro})")
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
        raise ReportNonDisponibile("Valori inattesi nella tabella del report") from errore


def invio_http(host: str, timeout_s: float = 60) -> Invia:
    """POST con `requests` (dipendenza dell'SDK di Databricks), sessione riusata."""
    import requests  # import pigro: in locale non serve

    base = host if host.startswith("https://") else f"https://{host}"
    url = f"{base.rstrip('/')}/api/2.0/sql/statements"
    sessione = requests.Session()

    def invia(token: str, corpo: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            risposta = sessione.post(
                url, json=corpo, headers={"Authorization": f"Bearer {token}"}, timeout=timeout_s
            )
        except requests.RequestException as errore:
            # Il messaggio di requests non contiene gli header (né il token).
            log.warning("Warehouse non raggiungibile: %s", type(errore).__name__)
            raise ReportNonDisponibile("Warehouse non raggiungibile") from errore
        try:
            dati: Any = risposta.json()
        except ValueError:
            dati = None
        if not isinstance(dati, dict):
            return risposta.status_code, {}
        return risposta.status_code, cast(dict[str, Any], dati)

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
