"""Regole di business delle iscrizioni. La transazione la apre e la chiude il chiamante."""

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Iscrizione
from academy_hub.dominio.errori import EdizioneCancellata
from academy_hub.dominio.stati import (
    StatoIscrizione,
    TransizioneNonConsentita,
    verifica_transizione,
)
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
    Solo da `Approvata`: `InAttesa → Confermata` spetta alla promozione, in ordine (R4).
    """
    edizione = repository.blocca_edizione(sessione, repository.edizione_di(sessione, iscrizione_id))
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    if iscrizione.stato is not StatoIscrizione.APPROVATA:
        raise TransizioneNonConsentita(iscrizione.stato, StatoIscrizione.CONFERMATA)
    if edizione.cancellata_il is not None:
        raise EdizioneCancellata(edizione.id)

    if edizione.posti_confermati < edizione.capienza:
        edizione.posti_confermati += 1
        nuovo = StatoIscrizione.CONFERMATA
    else:
        nuovo = StatoIscrizione.IN_ATTESA
    _cambia_stato(sessione, iscrizione, nuovo, autore_id)
    return nuovo
