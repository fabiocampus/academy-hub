"""Accesso ai dati di iscrizioni, edizioni ed eventi di audit. Unico posto con le query."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, EventoAudit, Iscrizione
from academy_hub.dominio.stati import StatoIscrizione


class IscrizioneNonTrovata(LookupError):
    def __init__(self, iscrizione_id: int) -> None:
        self.iscrizione_id = iscrizione_id
        super().__init__(f"Iscrizione {iscrizione_id} inesistente")


def blocca_iscrizione(sessione: Session, iscrizione_id: int) -> Iscrizione:
    """`SELECT … FOR UPDATE` sull'iscrizione, con i valori freschi dal database.

    Ordine dei lock in tutto il codice: prima l'iscrizione, poi la sua edizione.
    """
    iscrizione = sessione.scalar(
        select(Iscrizione)
        .where(Iscrizione.id == iscrizione_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if iscrizione is None:
        raise IscrizioneNonTrovata(iscrizione_id)
    return iscrizione


def blocca_edizione(sessione: Session, edizione_id: int) -> Edizione:
    """`SELECT … FOR UPDATE` sull'edizione: serializza chi tocca `posti_confermati` (R3)."""
    return sessione.scalars(
        select(Edizione)
        .where(Edizione.id == edizione_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def registra_evento(
    sessione: Session,
    iscrizione: Iscrizione,
    stato_a: StatoIscrizione,
    autore_id: int | None,
    motivo: str | None = None,
) -> None:
    sessione.add(
        EventoAudit(
            iscrizione_id=iscrizione.id,
            autore_id=autore_id,
            stato_da=iscrizione.stato,
            stato_a=stato_a,
            motivo=motivo,
        )
    )


def eventi_audit(sessione: Session, iscrizione_id: int) -> list[EventoAudit]:
    """Storia di un'iscrizione in ordine cronologico (US-11)."""
    return list(
        sessione.scalars(
            select(EventoAudit)
            .where(EventoAudit.iscrizione_id == iscrizione_id)
            .order_by(EventoAudit.avvenuto_il, EventoAudit.id)
        )
    )
