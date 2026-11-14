"""Accesso ai dati delle persone."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Persona
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.ruoli import Ruolo


def attore(sessione: Session, persona_id: int) -> Attore | None:
    riga = sessione.execute(
        select(Persona.team_id, Persona.ruoli).where(Persona.id == persona_id)
    ).one_or_none()
    if riga is None:
        return None
    return Attore(persona_id, riga.team_id, frozenset(Ruolo(r) for r in riga.ruoli))
