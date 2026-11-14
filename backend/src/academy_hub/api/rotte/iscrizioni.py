"""Rotte delle iscrizioni (US-04..US-11).

I cambi di stato sono comandi (`POST /iscrizioni/{id}/<azione>`), non PATCH: lo stato
si verifica sotto lock, quindi niente `If-Match` (ADR-0005, punto 3).
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from academy_hub.api import PREFISSO
from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import (
    CorsoInBreve,
    EventoLetto,
    IscrizioneConStoria,
    IscrizioneLetta,
    NuovaIscrizione,
    PaginaMieIscrizioni,
    PaginaRichieste,
    PersonaInBreve,
    RichiestaDaApprovare,
    Rifiuto,
    VoceMiaIscrizione,
)
from academy_hub.config import impostazioni
from academy_hub.servizi import iscrizioni

router = APIRouter(prefix="/iscrizioni", tags=["iscrizioni"], responses=risposte(401))
richieste = APIRouter(
    prefix="/richieste-da-approvare", tags=["iscrizioni"], responses=risposte(401, 422)
)

Limite = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=risposte(403, 409, 422),
    operation_id="richiediIscrizione",
    summary="Chiede l'iscrizione a un'edizione (idempotente con Idempotency-Key)",
)
def richiedi_iscrizione(
    dati: NuovaIscrizione,
    sessione: SessioneDb,
    attore: AttoreCorrente,
    risposta: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            pattern=r"^[!-~]{1,64}$",
            description="Facoltativa (consigliato un UUID). Ripetendo la richiesta con la "
            "stessa chiave si riceve la stessa iscrizione, nello stato attuale (ADR-0006).",
        ),
    ] = None,
) -> IscrizioneLetta:
    creata = iscrizioni.richiedi_iscrizione(sessione, attore, dati.edizione_id, idempotency_key)
    risposta.headers["Location"] = f"{PREFISSO}{router.prefix}/{creata.id}"
    return IscrizioneLetta.model_validate(creata)


@router.get("", responses=risposte(422), operation_id="mieIscrizioni")
def mie_iscrizioni(
    sessione: SessioneDb, attore: AttoreCorrente, limite: Limite = 20, offset: Offset = 0
) -> PaginaMieIscrizioni:
    voci, totale = iscrizioni.mie_iscrizioni(sessione, attore, limite, offset)
    return PaginaMieIscrizioni(
        elementi=[
            VoceMiaIscrizione(
                **IscrizioneLetta.model_validate(v.iscrizione).model_dump(),
                corso=CorsoInBreve.model_validate(v.corso),
                data_inizio=v.edizione.data_inizio,
                data_fine=v.edizione.data_fine,
                posizione_lista_attesa=v.posizione_lista_attesa,
            )
            for v in voci
        ],
        totale=totale,
        limite=limite,
        offset=offset,
    )


@router.get("/{iscrizione_id}", responses=risposte(403, 404), operation_id="leggiIscrizione")
def leggi_iscrizione(
    iscrizione_id: int, sessione: SessioneDb, attore: AttoreCorrente
) -> IscrizioneConStoria:
    trovata, storia = iscrizioni.leggi_iscrizione(sessione, attore, iscrizione_id)
    return IscrizioneConStoria(
        **IscrizioneLetta.model_validate(trovata).model_dump(),
        storia=[EventoLetto.model_validate(e) for e in storia],
    )


@router.post(
    "/{iscrizione_id}/approvazione",
    responses=risposte(403, 404, 409),
    operation_id="approvaIscrizione",
    summary="Il responsabile diretto approva una Richiesta",
)
def approva(iscrizione_id: int, sessione: SessioneDb, attore: AttoreCorrente) -> IscrizioneLetta:
    return IscrizioneLetta.model_validate(iscrizioni.approva(sessione, attore, iscrizione_id))


@router.post(
    "/{iscrizione_id}/rifiuto",
    responses=risposte(403, 404, 409, 422),
    operation_id="rifiutaIscrizione",
    summary="Il responsabile diretto rifiuta una Richiesta, con motivo",
)
def rifiuta(
    iscrizione_id: int, dati: Rifiuto, sessione: SessioneDb, attore: AttoreCorrente
) -> IscrizioneLetta:
    return IscrizioneLetta.model_validate(
        iscrizioni.rifiuta(sessione, attore, iscrizione_id, dati.motivo)
    )


@router.post(
    "/{iscrizione_id}/conferma",
    responses=risposte(403, 404, 409),
    operation_id="confermaIscrizione",
    summary="L'Academy conferma un'Approvata: Confermata se c'è posto, altrimenti InAttesa",
)
def conferma(iscrizione_id: int, sessione: SessioneDb, attore: AttoreCorrente) -> IscrizioneLetta:
    return IscrizioneLetta.model_validate(
        iscrizioni.conferma_posto(sessione, attore, iscrizione_id)
    )


@router.post(
    "/{iscrizione_id}/annullamento",
    responses=risposte(403, 404, 409),
    operation_id="annullaIscrizione",
    summary="Il titolare annulla la propria iscrizione (Confermata: entro la scadenza)",
)
def annulla(iscrizione_id: int, sessione: SessioneDb, attore: AttoreCorrente) -> IscrizioneLetta:
    scadenza = impostazioni().scadenza_annullamento_giorni
    return IscrizioneLetta.model_validate(
        iscrizioni.annulla(sessione, attore, iscrizione_id, scadenza)
    )


@richieste.get("", operation_id="richiesteDaApprovare")
def richieste_da_approvare(
    sessione: SessioneDb, attore: AttoreCorrente, limite: Limite = 20, offset: Offset = 0
) -> PaginaRichieste:
    """Le Richieste su cui sono il responsabile diretto, dalla più vecchia (US-07)."""
    voci, totale = iscrizioni.richieste_da_decidere(sessione, attore, limite, offset)
    return PaginaRichieste(
        elementi=[
            RichiestaDaApprovare(
                iscrizione_id=v.iscrizione.id,
                persona=PersonaInBreve.model_validate(v.persona),
                edizione_id=v.edizione.id,
                corso=CorsoInBreve.model_validate(v.corso),
                data_inizio=v.edizione.data_inizio,
                richiesta_il=v.iscrizione.richiesta_il,
            )
            for v in voci
        ],
        totale=totale,
        limite=limite,
        offset=offset,
    )
