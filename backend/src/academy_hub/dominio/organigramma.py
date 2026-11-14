"""Chi decide su una richiesta d'iscrizione: il responsabile diretto (R2, D7, D9).

La regola lavora sulla *catena dei responsabili* del richiedente: il responsabile del
suo team, poi quello del team padre, e così via fino al vertice (`None` per un team
senza responsabile). Il responsabile diretto è il primo della catena diverso dal
richiedente; se non c'è, decide l'amministrazione Academy. La catena si legge al
momento della decisione, quindi conta l'organigramma attuale (D9).

`repository.iscrizioni.richieste_da_decidere` applica la stessa regola in SQL per
l'elenco di US-07; `tests/test_api_approvazione.py` verifica che le due coincidano.
"""

from collections.abc import Sequence
from enum import Enum
from typing import Literal

from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import AzioneNonConsentita
from academy_hub.dominio.ruoli import Ruolo


class Amministrazione(Enum):
    """Decide un qualunque amministratore Academy (richieste dal vertice dell'organigramma)."""

    AMMINISTRAZIONE = "amministrazione"


AMMINISTRAZIONE = Amministrazione.AMMINISTRAZIONE

Decisore = int | Literal[Amministrazione.AMMINISTRAZIONE]


class AutoApprovazione(AzioneNonConsentita):
    tipo = "auto-approvazione"
    titolo = "Nessuno decide sulle proprie richieste"


class NonResponsabileDiretto(AzioneNonConsentita):
    tipo = "non-responsabile-diretto"
    titolo = "Decide solo il responsabile diretto del richiedente"


def responsabile_diretto(richiedente_id: int, catena: Sequence[int | None]) -> Decisore:
    for responsabile in catena:
        if responsabile is not None and responsabile != richiedente_id:
            return responsabile
    return AMMINISTRAZIONE


def verifica_decisore(attore: Attore, richiedente_id: int, catena: Sequence[int | None]) -> None:
    """R2: solo il responsabile diretto decide, e mai sulle proprie richieste."""
    if attore.persona_id == richiedente_id:
        raise AutoApprovazione("Non puoi decidere su una tua richiesta")
    decisore = responsabile_diretto(richiedente_id, catena)
    if decisore is AMMINISTRAZIONE:
        if not attore.ha_ruolo(Ruolo.ADMIN_ACADEMY):
            raise NonResponsabileDiretto("Questa richiesta la decide l'amministrazione Academy")
    elif decisore != attore.persona_id:
        raise NonResponsabileDiretto("Non sei il responsabile diretto del richiedente")
