"""Regole di business delle iscrizioni (US-04..US-11). La transazione la apre e la chiude
il chiamante.

Lock, sempre in quest'ordine (ADR-0004, ADR-0006): edizione, poi persona o iscrizione.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, EventoAudit, Iscrizione
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import (
    AzioneNonConsentita,
    Conflitto,
    DatiNonValidi,
    EdizioneCancellata,
    EdizioneIniziata,
    NonTrovato,
)
from academy_hub.dominio.organigramma import verifica_decisore
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import (
    StatoIscrizione,
    TransizioneNonConsentita,
    verifica_transizione,
)
from academy_hub.dominio.tempo import oggi
from academy_hub.repository import catalogo, persone
from academy_hub.repository import iscrizioni as repository
from academy_hub.repository.iscrizioni import RichiestaDaDecidere, VoceMiaIscrizione

S = StatoIscrizione


class IscrizioneDuplicata(Conflitto):
    """R1: al massimo una iscrizione attiva per persona ed edizione."""

    tipo = "iscrizione-duplicata"
    titolo = "Iscrizione attiva già presente"


class ScadenzaAnnullamentoSuperata(Conflitto):
    """R5: una Confermata si annulla solo fino a N giorni prima dell'inizio."""

    tipo = "scadenza-annullamento-superata"
    titolo = "Scadenza di annullamento superata"


class ChiaveIdempotenzaRiusata(DatiNonValidi):
    """La stessa `Idempotency-Key` con una richiesta diversa (altra edizione)."""

    tipo = "chiave-idempotenza-riusata"
    titolo = "Chiave di idempotenza già usata per un'altra richiesta"

    def __init__(self) -> None:
        super().__init__("Idempotency-Key", "già usata per un'altra edizione: generane una nuova")


def _cambia_stato(
    sessione: Session,
    iscrizione: Iscrizione,
    nuovo: StatoIscrizione,
    autore_id: int | None,
    motivo: str | None = None,
    edizione: Edizione | None = None,
) -> None:
    """Unico punto in cui un'iscrizione cambia stato: R7, poi i dati derivati, poi l'audit (R6).

    Chi entra in `Confermata` o ne esce deve passare l'edizione già bloccata: qui si
    aggiorna `posti_confermati` (ADR-0004).
    """
    verifica_transizione(iscrizione.stato, nuovo)
    if S.CONFERMATA in (iscrizione.stato, nuovo):
        if edizione is None or edizione.id != iscrizione.edizione_id:
            raise ValueError("Per entrare in Confermata o uscirne serve l'edizione bloccata")
        edizione.posti_confermati += 1 if nuovo is S.CONFERMATA else -1
    if nuovo is S.APPROVATA:
        iscrizione.approvata_il = datetime.now(UTC)
    repository.registra_evento(sessione, iscrizione.id, iscrizione.stato, nuovo, autore_id, motivo)
    iscrizione.stato = nuovo


def _verifica_aperta(edizione: Edizione) -> None:
    if edizione.cancellata_il is not None:
        raise EdizioneCancellata(edizione.id)
    if edizione.data_inizio <= oggi():
        raise EdizioneIniziata(edizione.id)


# --- US-04 · Chiedere l'iscrizione -------------------------------------------------


def richiedi_iscrizione(
    sessione: Session, attore: Attore, edizione_id: int, chiave: str | None = None
) -> Iscrizione:
    """Nuova iscrizione `Richiesta`; con la stessa `chiave` restituisce quella già creata.

    Il lock sulla persona mette in fila le sue richieste: i controlli sulla chiave e su R1
    sono letture semplici, senza intercettare violazioni di vincoli (ADR-0006).
    """
    attore.richiedi(Ruolo.DIPENDENTE)
    try:
        edizione = repository.blocca_edizione_in_lettura(sessione, edizione_id)
    except NonTrovato:
        raise DatiNonValidi("edizione_id", "edizione inesistente") from None
    persone.blocca_persona(sessione, attore.persona_id)

    if chiave is not None:
        precedente = repository.iscrizione_per_chiave(sessione, attore.persona_id, chiave)
        if precedente is not None:
            if precedente.edizione_id != edizione_id:
                raise ChiaveIdempotenzaRiusata
            return precedente

    _verifica_aperta(edizione)
    if repository.ha_iscrizione_attiva(sessione, attore.persona_id, edizione_id):
        raise IscrizioneDuplicata(f"Hai già un'iscrizione attiva all'edizione {edizione_id}")
    nuova = Iscrizione(
        persona_id=attore.persona_id,
        edizione_id=edizione_id,
        stato=S.RICHIESTA,
        chiave_idempotenza=chiave,
    )
    repository.aggiungi(sessione, nuova)
    repository.registra_evento(sessione, nuova.id, None, S.RICHIESTA, attore.persona_id)
    return nuova


# --- US-05, US-11 · Consultare -----------------------------------------------------


def mie_iscrizioni(
    sessione: Session, attore: Attore, limite: int = 20, offset: int = 0
) -> tuple[list[VoceMiaIscrizione], int]:
    return repository.mie_iscrizioni(sessione, attore.persona_id, limite, offset)


def leggi_iscrizione(
    sessione: Session, attore: Attore, iscrizione_id: int
) -> tuple[Iscrizione, list[EventoAudit]]:
    """L'iscrizione con la sua storia: la vedono il titolare e l'amministratore Academy."""
    trovata = repository.iscrizione(sessione, iscrizione_id)
    if trovata.persona_id != attore.persona_id and not attore.ha_ruolo(Ruolo.ADMIN_ACADEMY):
        raise AzioneNonConsentita("Puoi vedere solo le tue iscrizioni")
    return trovata, repository.eventi_audit(sessione, iscrizione_id)


# --- US-06, US-07 · Approvare o rifiutare ------------------------------------------


def _decidi(
    sessione: Session,
    attore: Attore,
    iscrizione_id: int,
    nuovo: StatoIscrizione,
    motivo: str | None = None,
) -> Iscrizione:
    """Prima chi decide (R2), poi lo stato (R7): chi non può decidere non scopre lo stato.

    Il lock sull'iscrizione basta: la decisione non tocca i posti. Due decisioni
    simultanee si mettono in fila; la seconda trova lo stato cambiato (409).
    """
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    catena = persone.catena_responsabili(sessione, iscrizione.persona_id)
    verifica_decisore(attore, iscrizione.persona_id, catena)
    verifica_transizione(iscrizione.stato, nuovo)
    if nuovo is S.APPROVATA:
        _verifica_aperta(catalogo.edizione(sessione, iscrizione.edizione_id))
    _cambia_stato(sessione, iscrizione, nuovo, attore.persona_id, motivo)
    return iscrizione


def approva(sessione: Session, attore: Attore, iscrizione_id: int) -> Iscrizione:
    return _decidi(sessione, attore, iscrizione_id, S.APPROVATA)


def rifiuta(sessione: Session, attore: Attore, iscrizione_id: int, motivo: str) -> Iscrizione:
    """Il rifiuto resta possibile anche a edizione iniziata: chiude la richiesta."""
    return _decidi(sessione, attore, iscrizione_id, S.RIFIUTATA, motivo)


def richieste_da_decidere(
    sessione: Session, attore: Attore, limite: int = 20, offset: int = 0
) -> tuple[list[RichiestaDaDecidere], int]:
    return repository.richieste_da_decidere(
        sessione, attore.persona_id, attore.ha_ruolo(Ruolo.ADMIN_ACADEMY), limite, offset
    )


# --- US-08 · Confermare un posto ---------------------------------------------------


def conferma_posto(sessione: Session, attore: Attore, iscrizione_id: int) -> Iscrizione:
    """Conferma Academy di un'iscrizione Approvata: Confermata se c'è posto, altrimenti InAttesa.

    Il lock sull'edizione serializza le conferme simultanee: chi arriva dopo legge
    `posti_confermati` aggiornato (R3). Il CHECK sulla capienza resta come ultima difesa.
    Solo da `Approvata`: `InAttesa → Confermata` spetta alla promozione, in ordine (R4).
    """
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    edizione = repository.blocca_edizione(sessione, repository.edizione_di(sessione, iscrizione_id))
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    if iscrizione.stato is not S.APPROVATA:
        raise TransizioneNonConsentita(iscrizione.stato, S.CONFERMATA)
    _verifica_aperta(edizione)

    nuovo = S.CONFERMATA if edizione.posti_confermati < edizione.capienza else S.IN_ATTESA
    _cambia_stato(sessione, iscrizione, nuovo, attore.persona_id, edizione=edizione)
    return iscrizione


# --- US-10 · Annullare la propria iscrizione ---------------------------------------


def annulla(
    sessione: Session, attore: Attore, iscrizione_id: int, scadenza_giorni: int
) -> Iscrizione:
    """Il titolare annulla la propria iscrizione attiva.

    `Confermata` solo se mancano più di `scadenza_giorni` giorni di calendario all'inizio
    (R5, D11): il valore arriva dalla configurazione dell'ambiente.
    """
    edizione = repository.blocca_edizione(sessione, repository.edizione_di(sessione, iscrizione_id))
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    if iscrizione.persona_id != attore.persona_id:
        raise AzioneNonConsentita("Puoi annullare solo le tue iscrizioni")
    verifica_transizione(iscrizione.stato, S.ANNULLATA)
    if iscrizione.stato is S.CONFERMATA:
        mancano = (edizione.data_inizio - oggi()).days
        if mancano <= scadenza_giorni:
            raise ScadenzaAnnullamentoSuperata(
                f"Mancano {mancano} giorni all'inizio: si annulla solo fino a "
                f"{scadenza_giorni + 1} giorni prima"
            )
    _cambia_stato(sessione, iscrizione, S.ANNULLATA, attore.persona_id, edizione=edizione)
    # TODO(US-09, terza PR della fase 5): un posto liberato passa al primo in lista d'attesa.
    return iscrizione
