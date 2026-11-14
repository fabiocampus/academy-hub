"""Accesso ai dati delle persone e dell'organigramma."""

from sqlalchemy import CTE, ColumnElement, Integer, literal, select
from sqlalchemy.orm import Session, aliased

from academy_hub.db.modelli import Persona, Team
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import NonTrovato
from academy_hub.dominio.ruoli import Ruolo

# Difesa da una gerarchia ciclica (il database impedisce solo il team padre di se stesso).
PROFONDITA_MASSIMA = 50


def attore(sessione: Session, persona_id: int) -> Attore | None:
    return _attore(sessione, Persona.id == persona_id)


def attore_per_email(sessione: Session, email: str) -> Attore | None:
    """Persona con quell'email (minuscola: vincolo `email_minuscola`)."""
    return _attore(sessione, Persona.email == email)


def _attore(sessione: Session, condizione: ColumnElement[bool]) -> Attore | None:
    riga = sessione.execute(
        select(Persona.id, Persona.team_id, Persona.ruoli).where(condizione)
    ).one_or_none()
    if riga is None:
        return None
    return Attore(riga.id, riga.team_id, frozenset(Ruolo(r) for r in riga.ruoli))


def blocca_persona(sessione: Session, persona_id: int) -> None:
    """Lock sulla persona: mette in fila le sue richieste d'iscrizione (R1, idempotenza)."""
    trovata = sessione.scalar(
        select(Persona.id).where(Persona.id == persona_id).with_for_update(key_share=True)
    )
    if trovata is None:
        raise NonTrovato("Persona", persona_id)


def antenati() -> CTE:
    """Ogni team con se stesso e i suoi antenati: (team_id, antenato_id, livello); 0 = sé."""
    base = select(
        Team.id.label("team_id"),
        Team.id.label("antenato_id"),
        literal(0, Integer).label("livello"),
    ).cte("antenati", recursive=True)
    padre = aliased(Team)
    return base.union_all(
        select(base.c.team_id, padre.team_padre_id, base.c.livello + 1)
        .join(padre, padre.id == base.c.antenato_id)
        .where(padre.team_padre_id.is_not(None), base.c.livello < PROFONDITA_MASSIMA)
    )


def catena_responsabili(sessione: Session, persona_id: int) -> list[int | None]:
    """Responsabili dal team della persona fino al vertice (`dominio.organigramma`)."""
    albero = antenati()
    return list(
        sessione.scalars(
            select(Team.responsabile_id)
            .select_from(Persona)
            .join(albero, albero.c.team_id == Persona.team_id)
            .join(Team, Team.id == albero.c.antenato_id)
            .where(Persona.id == persona_id)
            .order_by(albero.c.livello)
        )
    )
