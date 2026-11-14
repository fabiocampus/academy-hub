"""Accesso ai dati di corsi ed edizioni e query del catalogo."""

from dataclasses import dataclass
from datetime import date
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione, Iscrizione
from academy_hub.dominio.errori import NonTrovato
from academy_hub.dominio.stati import STATI_ATTIVI, StatoIscrizione


def corso(sessione: Session, corso_id: int) -> Corso:
    trovato = sessione.get(Corso, corso_id)
    if trovato is None:
        raise NonTrovato("Corso", corso_id)
    return trovato


def blocca_corso(sessione: Session, corso_id: int) -> Corso:
    trovato = sessione.scalar(
        select(Corso)
        .where(Corso.id == corso_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if trovato is None:
        raise NonTrovato("Corso", corso_id)
    return trovato


def blocca_corso_in_lettura(sessione: Session, corso_id: int) -> Corso:
    """FOR SHARE: il corso non cambia (né viene archiviato) fino alla fine della transazione."""
    trovato = sessione.scalar(
        select(Corso)
        .where(Corso.id == corso_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if trovato is None:
        raise NonTrovato("Corso", corso_id)
    return trovato


def aggiungi(sessione: Session, oggetto: object) -> None:
    sessione.add(oggetto)
    sessione.flush()


def edizione(sessione: Session, edizione_id: int) -> Edizione:
    trovata = sessione.get(Edizione, edizione_id)
    if trovata is None:
        raise NonTrovato("Edizione", edizione_id)
    return trovata


@dataclass(frozen=True)
class VoceCatalogo:
    edizione: Edizione
    corso: Corso
    lista_attesa: int
    mia_iscrizione: StatoIscrizione | None


def _escape_like(testo: str) -> str:
    return testo.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def catalogo(
    sessione: Session,
    persona_id: int,
    dopo_il: date,
    titolo: str | None,
    dal: date | None,
    al: date | None,
    limite: int,
    offset: int,
) -> tuple[list[VoceCatalogo], int]:
    """Edizioni che iniziano dopo `dopo_il`, non cancellate, di corsi non archiviati (US-03).

    Usa `ix_edizioni_catalogo`. Per ogni edizione: lunghezza della lista d'attesa e stato
    dell'iscrizione attiva di `persona_id` (al massimo una, per R1).
    """
    lista_attesa = (
        select(func.count())
        .where(Iscrizione.edizione_id == Edizione.id, Iscrizione.stato == StatoIscrizione.IN_ATTESA)
        .scalar_subquery()
    )
    mia = (
        select(Iscrizione.stato)
        .where(
            Iscrizione.edizione_id == Edizione.id,
            Iscrizione.persona_id == persona_id,
            Iscrizione.stato.in_(STATI_ATTIVI),
        )
        .scalar_subquery()
    )
    filtri = [
        Edizione.data_inizio > dopo_il,
        Edizione.cancellata_il.is_(None),
        Corso.archiviato_il.is_(None),
    ]
    if titolo:
        filtri.append(Corso.titolo.ilike(f"%{_escape_like(titolo)}%", escape="\\"))
    if dal is not None:
        filtri.append(Edizione.data_inizio >= dal)
    if al is not None:
        filtri.append(Edizione.data_inizio <= al)

    totale = sessione.scalar(select(func.count()).select_from(Edizione).join(Corso).where(*filtri))
    righe = sessione.execute(
        select(Edizione, Corso, lista_attesa, mia)
        .join(Corso)
        .where(*filtri)
        .order_by(Edizione.data_inizio, Edizione.id)
        .limit(limite)
        .offset(offset)
    ).all()
    # La sottoquery restituisce NULL senza iscrizione attiva, anche se il tipo non lo dice.
    voci = [VoceCatalogo(e, c, n, cast("StatoIscrizione | None", s)) for e, c, n, s in righe]
    return voci, totale or 0
