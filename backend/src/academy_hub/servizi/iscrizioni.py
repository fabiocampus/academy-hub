"""Regole di business delle iscrizioni. La transazione la apre e la chiude il chiamante."""

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Iscrizione
from academy_hub.dominio.stati import StatoIscrizione, verifica_transizione
from academy_hub.repository import iscrizioni as repository


def _cambia_stato(
    sessione: Session,
    iscrizione: Iscrizione,
    nuovo: StatoIscrizione,
    autore_id: int | None,
    motivo: str | None = None,
) -> None:
    """Unico punto in cui un'iscrizione cambia stato: R7 prima, poi l'audit (R6)."""
    verifica_transizione(iscrizione.stato, nuovo)
    repository.registra_evento(sessione, iscrizione, nuovo, autore_id, motivo)
    iscrizione.stato = nuovo


def conferma_posto(sessione: Session, iscrizione_id: int, autore_id: int) -> StatoIscrizione:
    """Conferma Academy di un'iscrizione Approvata: Confermata se c'è posto, altrimenti InAttesa.

    Il lock sull'edizione serializza le conferme simultanee: chi arriva dopo legge
    `posti_confermati` aggiornato (R3). Il CHECK sulla capienza resta come ultima difesa.
    """
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    verifica_transizione(iscrizione.stato, StatoIscrizione.CONFERMATA)
    edizione = repository.blocca_edizione(sessione, iscrizione.edizione_id)

    if edizione.posti_confermati < edizione.capienza:
        edizione.posti_confermati += 1
        nuovo = StatoIscrizione.CONFERMATA
    else:
        nuovo = StatoIscrizione.IN_ATTESA
    _cambia_stato(sessione, iscrizione, nuovo, autore_id)
    return nuovo
