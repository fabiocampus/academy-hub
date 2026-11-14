"""Rotte delle edizioni (US-02, US-18)."""

from fastapi import APIRouter, Response, status

from academy_hub.api import PREFISSO
from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb, VersioneAttesa, etag
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import EdizioneLetta, ModificaEdizione, NuovaEdizione
from academy_hub.servizi import catalogo

router = APIRouter(prefix="/edizioni", tags=["edizioni"], responses=risposte(401))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=risposte(403, 409, 422),
    operation_id="creaEdizione",
)
def crea_edizione(
    dati: NuovaEdizione, sessione: SessioneDb, attore: AttoreCorrente, risposta: Response
) -> EdizioneLetta:
    edizione = catalogo.crea_edizione(sessione, attore, **dati.model_dump())
    risposta.headers["Location"] = f"{PREFISSO}{router.prefix}/{edizione.id}"
    risposta.headers["ETag"] = etag(edizione.versione)
    return EdizioneLetta.model_validate(edizione)


@router.get("/{edizione_id}", responses=risposte(404), operation_id="leggiEdizione")
def leggi_edizione(
    edizione_id: int, sessione: SessioneDb, _attore: AttoreCorrente, risposta: Response
) -> EdizioneLetta:
    edizione = catalogo.leggi_edizione(sessione, edizione_id)
    risposta.headers["ETag"] = etag(edizione.versione)
    return EdizioneLetta.model_validate(edizione)


@router.patch(
    "/{edizione_id}",
    responses=risposte(403, 404, 409, 412, 422, 428),
    operation_id="modificaEdizione",
)
def modifica_edizione(
    edizione_id: int,
    dati: ModificaEdizione,
    sessione: SessioneDb,
    attore: AttoreCorrente,
    versione: VersioneAttesa,
    risposta: Response,
) -> EdizioneLetta:
    edizione = catalogo.modifica_edizione(
        sessione, attore, edizione_id, versione, **dati.model_dump(exclude_unset=True)
    )
    risposta.headers["ETag"] = etag(edizione.versione)
    return EdizioneLetta.model_validate(edizione)


@router.post(
    "/{edizione_id}/cancellazione",
    responses=risposte(403, 404, 409),
    operation_id="cancellaEdizione",
    summary="Cancella un'edizione non iniziata: le iscrizioni attive diventano Annullata",
)
def cancella_edizione(
    edizione_id: int, sessione: SessioneDb, attore: AttoreCorrente, risposta: Response
) -> EdizioneLetta:
    """Comando, come i cambi di stato delle iscrizioni: lo stato si verifica sotto lock,
    quindi niente `If-Match` (ADR-0005, punto 3). Ripetuto, restituisce l'edizione com'è."""
    edizione = catalogo.cancella_edizione(sessione, attore, edizione_id)
    risposta.headers["ETag"] = etag(edizione.versione)
    return EdizioneLetta.model_validate(edizione)
