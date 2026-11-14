"""Rotte dei corsi (US-01). Solo traduzione HTTP ↔ servizi: le regole stanno nei servizi."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from academy_hub.api import PREFISSO
from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb, VersioneAttesa, etag
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import (
    CorsoLetto,
    EdizioneLetta,
    ModificaCorso,
    NuovoCorso,
    PaginaCorsi,
    PaginaEdizioni,
    VoceEdizione,
)
from academy_hub.servizi import catalogo

router = APIRouter(prefix="/corsi", tags=["corsi"], responses=risposte(401))

Limite = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("", responses=risposte(403, 422), operation_id="elencoCorsi")
def elenco_corsi(
    sessione: SessioneDb,
    attore: AttoreCorrente,
    titolo: Annotated[str | None, Query(max_length=200, description="Parte del titolo")] = None,
    limite: Limite = 20,
    offset: Offset = 0,
) -> PaginaCorsi:
    """Tutti i corsi, archiviati compresi (dopo gli attivi), per titolo: per la gestione."""
    trovati, totale = catalogo.corsi(sessione, attore, titolo, limite, offset)
    return PaginaCorsi(
        elementi=[CorsoLetto.model_validate(c) for c in trovati],
        totale=totale,
        limite=limite,
        offset=offset,
    )


@router.get(
    "/{corso_id}/edizioni", responses=risposte(403, 404, 422), operation_id="edizioniDelCorso"
)
def edizioni_del_corso(
    corso_id: int,
    sessione: SessioneDb,
    attore: AttoreCorrente,
    limite: Limite = 20,
    offset: Offset = 0,
) -> PaginaEdizioni:
    """Le edizioni del corso, passate e cancellate comprese, dalla più lontana nel futuro."""
    voci, totale = catalogo.edizioni_del_corso(sessione, attore, corso_id, limite, offset)
    return PaginaEdizioni(
        elementi=[
            VoceEdizione(**EdizioneLetta.model_validate(e).model_dump(), lista_attesa=n)
            for e, n in voci
        ],
        totale=totale,
        limite=limite,
        offset=offset,
    )


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
