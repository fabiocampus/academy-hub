"""Stati dell'iscrizione e transizioni consentite (CONTEXT.md, R7)."""

from enum import StrEnum

from academy_hub.dominio.errori import Conflitto


class StatoIscrizione(StrEnum):
    RICHIESTA = "Richiesta"
    APPROVATA = "Approvata"
    RIFIUTATA = "Rifiutata"
    IN_ATTESA = "InAttesa"
    CONFERMATA = "Confermata"
    ANNULLATA = "Annullata"
    COMPLETATA = "Completata"

    @property
    def attivo(self) -> bool:
        """Conta per R1: al massimo una iscrizione attiva per persona ed edizione."""
        return self in STATI_ATTIVI


STATI_ATTIVI = frozenset(
    {
        StatoIscrizione.RICHIESTA,
        StatoIscrizione.APPROVATA,
        StatoIscrizione.IN_ATTESA,
        StatoIscrizione.CONFERMATA,
    }
)
# Attive ma senza posto: all'inizio dell'edizione diventano Annullata (D8).
STATI_PENDENTI = STATI_ATTIVI - {StatoIscrizione.CONFERMATA}

_S = StatoIscrizione
TRANSIZIONI: dict[StatoIscrizione, frozenset[StatoIscrizione]] = {
    _S.RICHIESTA: frozenset({_S.APPROVATA, _S.RIFIUTATA, _S.ANNULLATA}),
    _S.APPROVATA: frozenset({_S.CONFERMATA, _S.IN_ATTESA, _S.ANNULLATA}),
    _S.IN_ATTESA: frozenset({_S.CONFERMATA, _S.ANNULLATA}),
    _S.CONFERMATA: frozenset({_S.ANNULLATA, _S.COMPLETATA}),
    _S.RIFIUTATA: frozenset(),
    _S.ANNULLATA: frozenset(),
    _S.COMPLETATA: frozenset(),
}


class TransizioneNonConsentita(Conflitto):
    """Transizione non prevista dalla macchina a stati (R7)."""

    tipo = "transizione-non-consentita"
    titolo = "Transizione di stato non consentita"

    def __init__(self, da: StatoIscrizione, a: StatoIscrizione) -> None:
        self.da = da
        self.a = a
        super().__init__(f"Transizione non consentita: {da.value} → {a.value}")


def verifica_transizione(da: StatoIscrizione, a: StatoIscrizione) -> None:
    if a not in TRANSIZIONI[da]:
        raise TransizioneNonConsentita(da, a)
