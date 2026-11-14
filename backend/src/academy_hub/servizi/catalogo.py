"""Regole di corsi, edizioni e catalogo (US-01, US-02, US-03, US-18).

Come negli altri servizi, la transazione la apre e la chiude il chiamante.
"""

from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import (
    Conflitto,
    DatiNonValidi,
    EdizioneCancellata,
    EdizioneIniziata,
    NonTrovato,
    verifica_versione,
)
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import STATI_ATTIVI
from academy_hub.dominio.tempo import oggi
from academy_hub.repository import catalogo as repository
from academy_hub.repository import iscrizioni, persone
from academy_hub.repository.catalogo import VoceCatalogo
from academy_hub.servizi import iscrizioni as servizio_iscrizioni


class Invariato(Enum):
    """Campo assente dalla modifica, distinto da `None` che lo svuota."""

    INVARIATO = "invariato"


INVARIATO = Invariato.INVARIATO


class CorsoArchiviato(Conflitto):
    tipo = "corso-archiviato"
    titolo = "Corso archiviato"


class CapienzaSottoConfermati(Conflitto):
    """R3: la capienza non scende sotto le iscrizioni già confermate."""

    tipo = "capienza-sotto-confermati"
    titolo = "Capienza inferiore ai posti confermati"


def crea_corso(
    sessione: Session, attore: Attore, titolo: str, descrizione: str, durata_ore: int
) -> Corso:
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    corso = Corso(titolo=titolo, descrizione=descrizione, durata_ore=durata_ore)
    repository.aggiungi(sessione, corso)
    return corso


def leggi_corso(sessione: Session, corso_id: int) -> Corso:
    return repository.corso(sessione, corso_id)


def modifica_corso(
    sessione: Session,
    attore: Attore,
    corso_id: int,
    versione_attesa: int,
    titolo: str | None = None,
    descrizione: str | None = None,
    durata_ore: int | None = None,
) -> Corso:
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    corso = repository.blocca_corso(sessione, corso_id)
    verifica_versione(versione_attesa, corso.versione)
    if titolo is not None:
        corso.titolo = titolo
    if descrizione is not None:
        corso.descrizione = descrizione
    if durata_ore is not None:
        corso.durata_ore = durata_ore
    sessione.flush()
    return corso


def archivia_corso(sessione: Session, attore: Attore, corso_id: int, versione_attesa: int) -> Corso:
    """Fuori dal catalogo; le edizioni restano (report). Archiviare due volte non cambia nulla."""
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    corso = repository.blocca_corso(sessione, corso_id)
    verifica_versione(versione_attesa, corso.versione)
    if corso.archiviato_il is None:
        corso.archiviato_il = datetime.now(UTC)
        sessione.flush()
    return corso


def _verifica_docente(sessione: Session, docente_id: int | None) -> None:
    if docente_id is None:
        return
    docente = persone.attore(sessione, docente_id)
    if docente is None or not docente.ha_ruolo(Ruolo.DOCENTE):
        raise DatiNonValidi("docente_id", "persona inesistente o senza il ruolo docente")


def crea_edizione(
    sessione: Session,
    attore: Attore,
    corso_id: int,
    data_inizio: date,
    data_fine: date,
    capienza: int,
    docente_id: int | None = None,
) -> Edizione:
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    # FOR SHARE: un'archiviazione concorrente aspetta la fine di questa transazione.
    try:
        corso = repository.blocca_corso_in_lettura(sessione, corso_id)
    except NonTrovato:
        raise DatiNonValidi("corso_id", "corso inesistente") from None
    if corso.archiviato_il is not None:
        raise CorsoArchiviato(f"Il corso {corso_id} è archiviato")
    _verifica_docente(sessione, docente_id)
    edizione = Edizione(
        corso_id=corso_id,
        data_inizio=data_inizio,
        data_fine=data_fine,
        capienza=capienza,
        posti_confermati=0,
        docente_id=docente_id,
    )
    repository.aggiungi(sessione, edizione)
    return edizione


def leggi_edizione(sessione: Session, edizione_id: int) -> Edizione:
    return repository.edizione(sessione, edizione_id)


def modifica_edizione(
    sessione: Session,
    attore: Attore,
    edizione_id: int,
    versione_attesa: int,
    data_inizio: date | None = None,
    data_fine: date | None = None,
    capienza: int | None = None,
    docente_id: int | Literal[Invariato.INVARIATO] | None = INVARIATO,
) -> Edizione:
    """Modifica i campi passati; `docente_id=None` toglie il docente.

    Il lock sull'edizione rende affidabile il confronto con `posti_confermati` (R3).
    I posti nuovi di un aumento di capienza passano subito alla lista d'attesa (R4)."""
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    edizione = iscrizioni.blocca_edizione(sessione, edizione_id)
    verifica_versione(versione_attesa, edizione.versione)
    if edizione.cancellata_il is not None:
        raise EdizioneCancellata(edizione.id)
    inizio = edizione.data_inizio if data_inizio is None else data_inizio
    fine = edizione.data_fine if data_fine is None else data_fine
    if fine < inizio:
        raise DatiNonValidi("data_fine", "la data di fine precede quella di inizio")
    if capienza is not None and capienza < edizione.posti_confermati:
        raise CapienzaSottoConfermati(
            f"{edizione.posti_confermati} posti già confermati: la capienza non può scendere sotto"
        )
    if docente_id is not INVARIATO:
        _verifica_docente(sessione, docente_id)
    edizione.data_inizio, edizione.data_fine = inizio, fine
    if capienza is not None:
        edizione.capienza = capienza
    if docente_id is not INVARIATO:
        edizione.docente_id = docente_id
    servizio_iscrizioni.promuovi_dalla_lista(sessione, edizione)
    sessione.flush()
    return edizione


def cancella_edizione(sessione: Session, attore: Attore, edizione_id: int) -> Edizione:
    """Cancellazione logica di un'edizione non iniziata (US-18, D10).

    Sotto il lock dell'edizione ogni iscrizione attiva diventa `Annullata`, anche dentro
    la scadenza di R5. Le richieste nuove prendono l'edizione in `FOR SHARE` (ADR-0006):
    o finiscono prima e vengono annullate qui, o partono dopo e trovano l'edizione
    cancellata. Cancellare due volte non cambia nulla.
    """
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    edizione = iscrizioni.blocca_edizione(sessione, edizione_id)
    if edizione.cancellata_il is not None:
        return edizione
    if edizione.data_inizio <= oggi():
        raise EdizioneIniziata(edizione.id)
    servizio_iscrizioni.annulla_attive(
        sessione,
        edizione,
        STATI_ATTIVI,
        servizio_iscrizioni.MOTIVO_EDIZIONE_CANCELLATA,
        attore.persona_id,
    )
    edizione.cancellata_il = iscrizioni.adesso(sessione)
    sessione.flush()
    return edizione


def catalogo(
    sessione: Session,
    attore: Attore,
    titolo: str | None = None,
    dal: date | None = None,
    al: date | None = None,
    limite: int = 20,
    offset: int = 0,
) -> tuple[list[VoceCatalogo], int]:
    """Edizioni non ancora iniziate (calendario di Roma), per data di inizio (US-03)."""
    return repository.catalogo(sessione, attore.persona_id, oggi(), titolo, dal, al, limite, offset)
