"""Catalogo delle edizioni (US-03): paginato e filtrabile."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import CorsoInBreve, MiaIscrizione, PaginaCatalogo, VoceCatalogo
from academy_hub.servizi import catalogo

router = APIRouter(prefix="/catalogo", tags=["catalogo"], responses=risposte(401, 422))


@router.get("", operation_id="consultaCatalogo")
def consulta_catalogo(
    sessione: SessioneDb,
    attore: AttoreCorrente,
    titolo: Annotated[str | None, Query(max_length=200, description="Parte del titolo")] = None,
    dal: Annotated[date | None, Query(description="Inizio non prima di")] = None,
    al: Annotated[date | None, Query(description="Inizio non dopo")] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginaCatalogo:
    voci, totale = catalogo.catalogo(sessione, attore, titolo, dal, al, limite, offset)
    return PaginaCatalogo(
        elementi=[
            VoceCatalogo(
                edizione_id=v.edizione.id,
                corso=CorsoInBreve.model_validate(v.corso),
                data_inizio=v.edizione.data_inizio,
                data_fine=v.edizione.data_fine,
                capienza=v.edizione.capienza,
                posti_confermati=v.edizione.posti_confermati,
                lista_attesa=v.lista_attesa,
                mia_iscrizione=None
                if v.mia_iscrizione is None
                else MiaIscrizione(stato=v.mia_iscrizione),
            )
            for v in voci
        ],
        totale=totale,
        limite=limite,
        offset=offset,
    )
