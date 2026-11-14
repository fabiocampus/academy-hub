"""Regole di business delle iscrizioni (US-04..US-11, US-09, US-17). La transazione la apre
e la chiude il chiamante.

Lock, sempre in quest'ordine (ADR-0004, ADR-0006): edizione, poi persona o iscrizione.
"""

from collections.abc import Collection

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
    STATI_PENDENTI,
    StatoIscrizione,
    TransizioneNonConsentita,
    verifica_transizione,
)
from academy_hub.dominio.tempo import oggi
from academy_hub.repository import catalogo, persone
from academy_hub.repository import iscrizioni as repository
from academy_hub.repository.iscrizioni import RichiestaDaDecidere, VoceMiaIscrizione

S = StatoIscrizione

# Motivi degli annullamenti in blocco, scritti nell'audit (D8, D10).
MOTIVO_EDIZIONE_INIZIATA = "edizione-iniziata"
MOTIVO_EDIZIONE_CANCELLATA = "edizione-cancellata"


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
    aggiorna `posti_confermati` (ADR-0004). Le date vengono dall'orologio del database,
    lo stesso di `richiesta_il` e dell'audit: `approvata_il` ordina la lista d'attesa (R4)
    e la risposta del comando riporta già l'istante del cambio.
    """
    verifica_transizione(iscrizione.stato, nuovo)
    if S.CONFERMATA in (iscrizione.stato, nuovo):
        if edizione is None or edizione.id != iscrizione.edizione_id:
            raise ValueError("Per entrare in Confermata o uscirne serve l'edizione bloccata")
        edizione.posti_confermati += 1 if nuovo is S.CONFERMATA else -1
    istante = repository.adesso(sessione)
    iscrizione.aggiornata_il = istante
    if nuovo is S.APPROVATA:
        iscrizione.approvata_il = istante
    repository.registra_evento(sessione, iscrizione.id, iscrizione.stato, nuovo, autore_id, motivo)
    iscrizione.stato = nuovo


def _verifica_aperta(edizione: Edizione) -> None:
    if edizione.cancellata_il is not None:
        raise EdizioneCancellata(edizione.id)
    if edizione.data_inizio <= oggi():
        raise EdizioneIniziata(edizione.id)


# --- US-09 · Promozione dalla lista d'attesa ---------------------------------------


def promuovi_dalla_lista(sessione: Session, edizione: Edizione) -> int:
    """Riempie i posti liberi con la lista d'attesa, in ordine di approvazione (R4).

    `edizione` va passata già bloccata. Autore il sistema; nessuna promozione a edizione
    iniziata o cancellata (D2). Restituisce quante iscrizioni ha promosso. La chiamano,
    nella stessa transazione, l'annullamento, la conferma, l'aumento di capienza e il
    job di rete di sicurezza (ADR-0007).
    """
    # Difensivo sulla cancellazione: un'edizione cancellata non ha più InAttesa (D10).
    if edizione.cancellata_il is not None or edizione.data_inizio <= oggi():
        return 0
    promosse = 0
    while edizione.posti_confermati < edizione.capienza:
        prima = repository.blocca_prima_in_attesa(sessione, edizione.id)
        if prima is None:
            break
        _cambia_stato(sessione, prima, S.CONFERMATA, None, edizione=edizione)
        promosse += 1
    return promosse


def annulla_attive(
    sessione: Session,
    edizione: Edizione,
    stati: Collection[StatoIscrizione],
    motivo: str,
    autore_id: int | None,
) -> int:
    """Annulla in blocco le iscrizioni dell'edizione negli `stati` dati, ignorando R5.

    `edizione` va passata già bloccata. Per la cancellazione (D10) e la scadenza (D8).
    """
    trovate = repository.blocca_iscrizioni(sessione, edizione.id, stati)
    for trovata in trovate:
        _cambia_stato(sessione, trovata, S.ANNULLATA, autore_id, motivo, edizione=edizione)
    return len(trovate)


# --- Job di sistema (US-17, rete di sicurezza di US-09) -----------------------------


def edizioni_da_chiudere(sessione: Session) -> list[int]:
    return repository.edizioni_iniziate_con_pendenti(sessione, oggi())


def chiudi_edizione_iniziata(sessione: Session, edizione_id: int) -> int:
    """D8: all'inizio dell'edizione le iscrizioni pendenti diventano Annullata (sistema).

    Idempotente: una seconda esecuzione non trova più pendenti e non scrive audit.
    """
    edizione = repository.blocca_edizione(sessione, edizione_id)
    if edizione.data_inizio > oggi():
        return 0
    return annulla_attive(sessione, edizione, STATI_PENDENTI, MOTIVO_EDIZIONE_INIZIATA, None)


def edizioni_da_promuovere(sessione: Session) -> list[int]:
    return repository.edizioni_con_posti_e_lista(sessione, oggi())


def promuovi_edizione(sessione: Session, edizione_id: int) -> int:
    return promuovi_dalla_lista(sessione, repository.blocca_edizione(sessione, edizione_id))


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
    Per lo stesso motivo, se ci sono posti liberi e lista d'attesa (stato che la promozione
    inline non lascia, ma il job ripara solo al suo giro), prima passa la lista.
    """
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    edizione = repository.blocca_edizione(sessione, repository.edizione_di(sessione, iscrizione_id))
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    if iscrizione.stato is not S.APPROVATA:
        raise TransizioneNonConsentita(iscrizione.stato, S.CONFERMATA)
    _verifica_aperta(edizione)
    promuovi_dalla_lista(sessione, edizione)

    nuovo = S.CONFERMATA if edizione.posti_confermati < edizione.capienza else S.IN_ATTESA
    _cambia_stato(sessione, iscrizione, nuovo, attore.persona_id, edizione=edizione)
    return iscrizione


# --- US-10 · Annullare la propria iscrizione ---------------------------------------


def annulla(
    sessione: Session, attore: Attore, iscrizione_id: int, scadenza_giorni: int
) -> Iscrizione:
    """Il titolare annulla la propria iscrizione attiva.

    `Confermata` solo se mancano più di `scadenza_giorni` giorni di calendario all'inizio
    (R5, D11): il valore arriva dalla configurazione dell'ambiente. Il posto liberato passa
    subito al primo in lista d'attesa, nella stessa transazione (R4).
    """
    # Titolare verificato prima dei lock: chi non può annullare non mette in fila le
    # conferme dell'edizione. La persona di un'iscrizione non cambia mai.
    if repository.iscrizione(sessione, iscrizione_id).persona_id != attore.persona_id:
        raise AzioneNonConsentita("Puoi annullare solo le tue iscrizioni")
    edizione = repository.blocca_edizione(sessione, repository.edizione_di(sessione, iscrizione_id))
    iscrizione = repository.blocca_iscrizione(sessione, iscrizione_id)
    verifica_transizione(iscrizione.stato, S.ANNULLATA)
    if iscrizione.stato is S.CONFERMATA:
        mancano = (edizione.data_inizio - oggi()).days
        if mancano <= scadenza_giorni:
            raise ScadenzaAnnullamentoSuperata(
                f"Mancano {mancano} giorni all'inizio: si annulla solo fino a "
                f"{scadenza_giorni + 1} giorni prima"
            )
    _cambia_stato(sessione, iscrizione, S.ANNULLATA, attore.persona_id, edizione=edizione)
    promuovi_dalla_lista(sessione, edizione)
    return iscrizione
