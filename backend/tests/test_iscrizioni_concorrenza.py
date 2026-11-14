"""Richieste e decisioni simultanee, chiamando i servizi da più connessioni (US-04, US-06)."""

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Iscrizione
from academy_hub.dominio.stati import StatoIscrizione, TransizioneNonConsentita
from academy_hub.servizi import iscrizioni
from academy_hub.servizi.iscrizioni import IscrizioneDuplicata

from .api import edizione, iscrizione, organigramma
from .concorrenza import attore, insieme

pytestmark = pytest.mark.integrazione


def conta(db: Engine) -> int:
    with Session(db) as sessione:
        return sessione.scalar(select(func.count()).select_from(Iscrizione)) or 0


@pytest.mark.parametrize("concorrenti", [2, 5])
def test_stessa_chiave_simultanea_una_sola_iscrizione(db: Engine, concorrenti: int) -> None:
    org = organigramma(db)
    anna = attore(db, org.ids["Anna"])
    edizione_id = edizione(db)

    esiti = insieme(
        db,
        [
            lambda s: iscrizioni.richiedi_iscrizione(s, anna, edizione_id, "chiave-1").id
            for _ in range(concorrenti)
        ],
    )

    assert len(set(esiti)) == 1, esiti
    assert isinstance(esiti[0], int)
    assert conta(db) == 1


def test_r1_richieste_simultanee_senza_chiave_una_sola_passa(db: Engine) -> None:
    org = organigramma(db)
    anna = attore(db, org.ids["Anna"])
    edizione_id = edizione(db)

    esiti = insieme(
        db,
        [lambda s: iscrizioni.richiedi_iscrizione(s, anna, edizione_id).id for _ in range(2)],
    )

    assert sum(isinstance(e, int) for e in esiti) == 1, esiti
    assert sum(isinstance(e, IscrizioneDuplicata) for e in esiti) == 1, esiti
    assert conta(db) == 1


@pytest.mark.parametrize("seconda", ["approva", "rifiuta"])
def test_us06_decisioni_simultanee_una_sola_passa(db: Engine, seconda: str) -> None:
    org = organigramma(db)
    rossa = attore(db, org.ids["Rossa"])
    iscrizione_id = iscrizione(db, org.ids["Anna"], edizione(db), StatoIscrizione.RICHIESTA)

    def approva(s: Session) -> StatoIscrizione:
        return iscrizioni.approva(s, rossa, iscrizione_id).stato

    def rifiuta(s: Session) -> StatoIscrizione:
        return iscrizioni.rifiuta(s, rossa, iscrizione_id, "Budget").stato

    esiti = insieme(db, [approva, approva if seconda == "approva" else rifiuta])

    assert sum(isinstance(e, StatoIscrizione) for e in esiti) == 1, esiti
    assert sum(isinstance(e, TransizioneNonConsentita) for e in esiti) == 1, esiti
    with Session(db) as sessione:
        anna = attore(db, org.ids["Anna"])
        _, storia = iscrizioni.leggi_iscrizione(sessione, anna, iscrizione_id)
    assert len(storia) == 1
