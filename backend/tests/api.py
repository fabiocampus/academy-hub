"""Aiuti per i test dell'API HTTP."""

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.dominio.ruoli import Ruolo

from .dati import crea_persona


def persona(db: Engine, nome: str, *ruoli: Ruolo) -> dict[str, str]:
    """Header d'identità di una persona nuova con i ruoli dati."""
    with Session(db) as sessione:
        p = crea_persona(sessione, nome, ruoli=ruoli or (Ruolo.DIPENDENTE,))
        sessione.commit()
        return {"X-Persona-Id": str(p.id)}
