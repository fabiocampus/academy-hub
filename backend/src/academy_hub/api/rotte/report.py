"""Report dalla parte analitica (issue #73): li legge Unity Catalog con l'identità
dell'utente, non con quella dell'App (ADR-0011)."""

from fastapi import APIRouter, Request, Response

from academy_hub.api.dipendenze import AttoreCorrente
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import (
    ReportIscrizioni,
    ReportOrePerTeam,
    ReportTassoCompletamento,
    ReportValutazioneMedia,
)
from academy_hub.report import (
    ORE_PER_TEAM,
    TASSO_COMPLETAMENTO,
    VALUTAZIONE_MEDIA,
    Gold,
    LettoreReport,
    ReportGold,
    T,
)

router = APIRouter(tags=["report"])

# Databricks Apps mette qui il token dell'utente quando l'App ha lo scope sql. Non è nel
# contratto: lo imposta il proxy, non il client.
INTESTAZIONE_ACCESSO = "x-forwarded-access-token"


@router.get(
    "/report/iscrizioni-per-corso",
    responses=risposte(401, 403, 503),
    operation_id="reportIscrizioniPerCorso",
    deprecated=True,
)
def iscrizioni_per_corso(
    richiesta: Request, risposta: Response, _attore: AttoreCorrente
) -> ReportIscrizioni:
    """Iscrizioni per corso dalla tabella sintetica della fase 8: sostituito dai report sul
    gold calcolato (ore per team, tasso di completamento, valutazione media). Basta essere
    una persona registrata: chi può leggere la tabella lo decide Unity Catalog."""
    lettore: LettoreReport = richiesta.app.state.report
    report = lettore.iscrizioni_per_corso(richiesta.headers.get(INTESTAZIONE_ACCESSO))
    # Dipende dai permessi di chi chiede: nessuna cache condivisa.
    risposta.headers["Cache-Control"] = "no-store"
    return ReportIscrizioni.model_validate(report)


def _gold(richiesta: Request, risposta: Response, report: Gold[T]) -> ReportGold[T]:
    lettore: LettoreReport = richiesta.app.state.report
    letto = lettore.gold(report, richiesta.headers.get(INTESTAZIONE_ACCESSO))
    risposta.headers["Cache-Control"] = "no-store"
    return letto


@router.get(
    "/report/ore-per-team",
    responses=risposte(401, 403, 503),
    operation_id="reportOrePerTeam",
)
def ore_per_team(
    richiesta: Request, risposta: Response, _attore: AttoreCorrente
) -> ReportOrePerTeam:
    """Ore di formazione per team (il team alla fine dell'edizione), dal gold (ADR-0017).
    Chi vede quali team lo decide Unity Catalog con l'identità della persona."""
    return ReportOrePerTeam.model_validate(_gold(richiesta, risposta, ORE_PER_TEAM))


@router.get(
    "/report/tasso-completamento",
    responses=risposte(401, 403, 503),
    operation_id="reportTassoCompletamento",
)
def tasso_completamento(
    richiesta: Request, risposta: Response, _attore: AttoreCorrente
) -> ReportTassoCompletamento:
    """Per corso: iscrizioni concluse, completate e tasso, dal gold (ADR-0017)."""
    return ReportTassoCompletamento.model_validate(_gold(richiesta, risposta, TASSO_COMPLETAMENTO))


@router.get(
    "/report/valutazione-media",
    responses=risposte(401, 403, 503),
    operation_id="reportValutazioneMedia",
)
def valutazione_media(
    richiesta: Request, risposta: Response, _attore: AttoreCorrente
) -> ReportValutazioneMedia:
    """Per corso: voto medio delle iscrizioni completate, dal gold (ADR-0017)."""
    return ReportValutazioneMedia.model_validate(_gold(richiesta, risposta, VALUTAZIONE_MEDIA))
