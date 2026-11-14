"""Chi è la persona collegata (issue #59)."""

from sqlalchemy.orm import Session

from academy_hub.dominio.attore import Attore
from academy_hub.repository import persone
from academy_hub.repository.persone import Profilo


def profilo(sessione: Session, attore: Attore) -> Profilo:
    """Ognuno legge solo il proprio profilo: non c'è un parametro per chiederne un altro."""
    return persone.profilo(sessione, attore.persona_id)
