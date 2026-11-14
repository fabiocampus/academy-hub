"""Persone: il profilo di chi è collegato (issue #59) e i docenti (issue #64)."""

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Persona
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.repository import persone
from academy_hub.repository.persone import Profilo


def profilo(sessione: Session, attore: Attore) -> Profilo:
    """Ognuno legge solo il proprio profilo: non c'è un parametro per chiederne un altro."""
    return persone.profilo(sessione, attore.persona_id)


def docenti(sessione: Session, attore: Attore) -> list[Persona]:
    """Chi può tenere un'edizione: serve all'amministrazione per sceglierlo."""
    attore.richiedi(Ruolo.ADMIN_ACADEMY)
    return persone.docenti(sessione)
