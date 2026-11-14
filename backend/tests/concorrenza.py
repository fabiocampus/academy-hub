"""Aiuti per i test di concorrenza: servizi chiamati da più connessioni insieme."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import ErroreDominio
from academy_hub.repository import persone

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
