"""Rotte dei corsi (US-01). Solo traduzione HTTP ↔ servizi: le regole stanno nei servizi."""

from fastapi import APIRouter, Response, status

from academy_hub.api import PREFISSO
from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb, VersioneAttesa, etag
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import CorsoLetto, ModificaCorso, NuovoCorso
from academy_hub.servizi import catalogo

router = APIRouter(prefix="/corsi", tags=["corsi"], responses=risposte(401))


@router.post(
    "", status_code=status.HTTP_201_CREATED, responses=risposte(403, 422), operation_id="creaCorso"
)
def crea_corso(
    dati: NuovoCorso, sessione: SessioneDb, attore: AttoreCorrente, risposta: Response
) -> CorsoLetto:
    corso = catalogo.crea_corso(sessione, attore, dati.titolo, dati.descrizione, dati.durata_ore)
    risposta.headers["Location"] = f"{PREFISSO}{router.prefix}/{corso.id}"
    risposta.headers["ETag"] = etag(corso.versione)
    return CorsoLetto.model_validate(corso)


@router.get("/{corso_id}", responses=risposte(404), operation_id="leggiCorso")
def leggi_corso(
    corso_id: int, sessione: SessioneDb, _attore: AttoreCorrente, risposta: Response
) -> CorsoLetto:
    corso = catalogo.leggi_corso(sessione, corso_id)
    risposta.headers["ETag"] = etag(corso.versione)
    return CorsoLetto.model_validate(corso)


@router.patch(
    "/{corso_id}", responses=risposte(403, 404, 412, 422, 428), operation_id="modificaCorso"
)
def modifica_corso(
    corso_id: int,
    dati: ModificaCorso,
    sessione: SessioneDb,
    attore: AttoreCorrente,
    versione: VersioneAttesa,
    risposta: Response,
) -> CorsoLetto:
    corso = catalogo.modifica_corso(
        sessione, attore, corso_id, versione, **dati.model_dump(exclude_none=True)
    )
    risposta.headers["ETag"] = etag(corso.versione)
    return CorsoLetto.model_validate(corso)


@router.post(
    "/{corso_id}/archiviazione",
    responses=risposte(403, 404, 412, 428),
    operation_id="archiviaCorso",
    summary="Archivia un corso: esce dal catalogo, le edizioni restano nei report",
)
def archivia_corso(
    corso_id: int,
    sessione: SessioneDb,
    attore: AttoreCorrente,
    versione: VersioneAttesa,
    risposta: Response,
) -> CorsoLetto:
    corso = catalogo.archivia_corso(sessione, attore, corso_id, versione)
    risposta.headers["ETag"] = etag(corso.versione)
    return CorsoLetto.model_validate(corso)
