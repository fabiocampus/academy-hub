"""Errori di dominio. Ognuno ha un `tipo` stabile, che l'API espone come `type` RFC 9457.

Le classi base dicono la natura dell'errore; il codice HTTP lo sceglie solo l'API
(`academy_hub.api.errori`), così servizi e dominio restano indipendenti dal web.
"""

from typing import ClassVar


class ErroreDominio(Exception):
    tipo: ClassVar[str] = "errore-dominio"
    titolo: ClassVar[str] = "Errore di dominio"


class NonAutenticato(ErroreDominio):
    tipo = "non-autenticato"
    titolo = "Identità mancante o non valida"


class AzioneNonConsentita(ErroreDominio):
    tipo = "azione-non-consentita"
    titolo = "Azione non consentita al tuo ruolo"


class PersonaNonRegistrata(AzioneNonConsentita):
    """Identità valida, ma nessuna persona con quell'email: non abilitata all'applicazione."""

    tipo = "persona-non-registrata"
    titolo = "Persona non registrata nell'Academy"


class ReportNonAutorizzato(AzioneNonConsentita):
    """Unity Catalog (o il warehouse) nega la lettura all'utente collegato (ADR-0011)."""

    tipo = "report-non-autorizzato"
    titolo = "Non hai i permessi per leggere questo report"


class ReportNonDisponibile(ErroreDominio):
    """Il report non si può leggere ora: configurazione, warehouse o tabella mancanti."""

    tipo = "report-non-disponibile"
    titolo = "Report non disponibile"


class FunzioneNonDisponibile(ErroreDominio):
    """Feature flag spenta in questo ambiente (ADR-0014): la rotta risponde come se non ci fosse."""

    tipo = "funzione-non-disponibile"
    titolo = "Funzione non disponibile in questo ambiente"


class NonTrovato(ErroreDominio, LookupError):
    tipo = "non-trovato"
    titolo = "Risorsa inesistente"

    def __init__(self, risorsa: str, risorsa_id: int) -> None:
        self.risorsa = risorsa
        self.risorsa_id = risorsa_id
        super().__init__(f"{risorsa} {risorsa_id} inesistente")


class Conflitto(ErroreDominio):
    """La richiesta è ben formata ma contrasta con lo stato attuale (R1, R3, R5, R7...)."""

    tipo = "conflitto"
    titolo = "Conflitto con lo stato attuale"


class EdizioneCancellata(Conflitto):
    tipo = "edizione-cancellata"
    titolo = "Edizione cancellata"

    def __init__(self, edizione_id: int) -> None:
        self.edizione_id = edizione_id
        super().__init__(f"Edizione {edizione_id} cancellata")


class EdizioneIniziata(Conflitto):
    """Edizione già iniziata (calendario di Roma): niente richieste, approvazioni, conferme."""

    tipo = "edizione-iniziata"
    titolo = "Edizione già iniziata"

    def __init__(self, edizione_id: int) -> None:
        self.edizione_id = edizione_id
        super().__init__(f"Edizione {edizione_id} già iniziata")


class DatiNonValidi(ErroreDominio):
    """Dati incoerenti che si scoprono solo confrontandoli con quelli salvati."""

    tipo = "dati-non-validi"
    titolo = "Dati non validi"

    def __init__(self, campo: str, messaggio: str) -> None:
        self.campo = campo
        self.messaggio = messaggio
        super().__init__(f"{campo}: {messaggio}")


class VersioneNonCorrispondente(ErroreDominio):
    """Concorrenza ottimistica: la risorsa è cambiata dopo che il client l'ha letta."""

    tipo = "versione-non-corrispondente"
    titolo = "La risorsa è stata modificata da qualcun altro"

    def __init__(self, attesa: int, attuale: int) -> None:
        self.attesa = attesa
        self.attuale = attuale
        super().__init__(f"Versione attesa {attesa}, attuale {attuale}: rileggi la risorsa")


def verifica_versione(attesa: int, attuale: int) -> None:
    if attesa != attuale:
        raise VersioneNonCorrispondente(attesa, attuale)
