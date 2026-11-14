"""Chi compie un'azione. Ruoli e team vengono dal database, non dal provider d'identità."""

from dataclasses import dataclass

from academy_hub.dominio.errori import AzioneNonConsentita
from academy_hub.dominio.ruoli import Ruolo


@dataclass(frozen=True)
class Attore:
    persona_id: int
    team_id: int
    ruoli: frozenset[Ruolo]

    def ha_ruolo(self, ruolo: Ruolo) -> bool:
        return ruolo in self.ruoli

    def richiedi(self, ruolo: Ruolo) -> None:
        if not self.ha_ruolo(ruolo):
            raise AzioneNonConsentita(f"Serve il ruolo {ruolo.value}")
