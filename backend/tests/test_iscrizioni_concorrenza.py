"""Richieste e decisioni simultanee, chiamando i servizi da più connessioni (US-04, US-06)."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Iscrizione
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import ErroreDominio
from academy_hub.dominio.stati import StatoIscrizione, TransizioneNonConsentita
from academy_hub.repository import persone
from academy_hub.servizi import iscrizioni
from academy_hub.servizi.iscrizioni import IscrizioneDuplicata

from .api import edizione, iscrizione, organigramma

pytestmark = pytest.mark.integrazione

T = TypeVar("T")


def attore(db: Engine, persona_id: int) -> Attore:
    with Session(db) as sessione:
        trovato = persone.attore(sessione, persona_id)
    assert trovato is not None
    return trovato


def insieme(db: Engine, azioni: list[Callable[[Session], T]]) -> list[T | ErroreDominio]:
    """Esegue le azioni in transazioni parallele, partite insieme; raccoglie esiti ed errori."""
    via = threading.Barrier(len(azioni), timeout=30)

    def esegui(azione: Callable[[Session], T]) -> T | ErroreDominio:
        try:
            with Session(db) as sessione, sessione.begin():
                sessione.connection()  # connessione aperta prima del via
                via.wait()
                return azione(sessione)
        except ErroreDominio as errore:
            return errore

    with ThreadPoolExecutor(max_workers=len(azioni)) as esecutore:
        return list(esecutore.map(esegui, azioni))


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


def test_us06_approvazioni_simultanee_una_sola_passa(db: Engine) -> None:
    org = organigramma(db)
    rossa = attore(db, org.ids["Rossa"])
    iscrizione_id = iscrizione(db, org.ids["Anna"], edizione(db), StatoIscrizione.RICHIESTA)

    esiti = insieme(
        db,
        [
            lambda s: iscrizioni.approva(s, rossa, iscrizione_id).stato,
            lambda s: iscrizioni.rifiuta(s, rossa, iscrizione_id, "Budget").stato,
        ],
    )

    assert sum(isinstance(e, StatoIscrizione) for e in esiti) == 1, esiti
    assert sum(isinstance(e, TransizioneNonConsentita) for e in esiti) == 1, esiti
    with Session(db) as sessione:
        anna = attore(db, org.ids["Anna"])
        _, storia = iscrizioni.leggi_iscrizione(sessione, anna, iscrizione_id)
    assert len(storia) == 1
