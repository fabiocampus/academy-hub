"""Report dalla parte analitica (issue #73): li legge Unity Catalog con l'identità
dell'utente, non con quella dell'App (ADR-0011)."""

from fastapi import APIRouter, Request, Response

from academy_hub.api.dipendenze import AttoreCorrente
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import ReportIscrizioni
from academy_hub.report import LettoreReport

router = APIRouter(tags=["report"])

# Databricks Apps mette qui il token dell'utente quando l'App ha lo scope sql. Non è nel
# contratto: lo imposta il proxy, non il client.
INTESTAZIONE_ACCESSO = "x-forwarded-access-token"


@router.get(
    "/report/iscrizioni-per-corso",
    responses=risposte(401, 403, 503),
    operation_id="reportIscrizioniPerCorso",
)
def iscrizioni_per_corso(
    richiesta: Request, risposta: Response, _attore: AttoreCorrente
) -> ReportIscrizioni:
    """Iscrizioni per corso dallo schema gold. Basta essere una persona registrata: chi
    può leggere la tabella lo decidono i permessi di Unity Catalog della persona."""
    lettore: LettoreReport = richiesta.app.state.report
    report = lettore.iscrizioni_per_corso(richiesta.headers.get(INTESTAZIONE_ACCESSO))
    # Dipende dai permessi di chi chiede: nessuna cache condivisa.
    risposta.headers["Cache-Control"] = "no-store"
    return ReportIscrizioni.model_validate(report)
