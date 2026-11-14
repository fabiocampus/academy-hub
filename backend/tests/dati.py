"""Dati sintetici per i test di integrazione. Nessun dato reale: domini `.test` (RFC 2606)."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione, Iscrizione, Persona, Team
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi


def crea_persona(
    sessione: Session,
    nome: str,
    team: Team | None = None,
    ruoli: tuple[Ruolo, ...] = (Ruolo.DIPENDENTE,),
) -> Persona:
    if team is None:
        team = Team(nome=f"Team di {nome}")
        sessione.add(team)
        sessione.flush()
    persona = Persona(
        nome=nome,
        email=f"{nome.lower()}@esempio.test",
        team_id=team.id,
        ruoli=[r.value for r in ruoli],
    )
    sessione.add(persona)
    sessione.flush()
    return persona


def crea_team(sessione: Session, nome: str, padre: Team | None = None) -> Team:
    team = Team(nome=nome, team_padre_id=None if padre is None else padre.id)
    sessione.add(team)
    sessione.flush()
    return team


def crea_edizione(
    sessione: Session,
    capienza: int = 10,
    posti_confermati: int = 0,
    inizio: date | None = None,
) -> Edizione:
    """Edizione di un corso nuovo; per difetto inizia fra 30 giorni (calendario di Roma)."""
    corso = Corso(titolo="SQL per analisti", durata_ore=8)
    sessione.add(corso)
    sessione.flush()
    inizio = oggi() + timedelta(days=30) if inizio is None else inizio
    edizione = Edizione(
        corso_id=corso.id,
        data_inizio=inizio,
        data_fine=inizio + timedelta(days=1),
        capienza=capienza,
        posti_confermati=posti_confermati,
    )
    sessione.add(edizione)
    sessione.flush()
    return edizione


def crea_iscrizione(
    sessione: Session,
    persona: Persona,
    edizione: Edizione,
    stato: StatoIscrizione = StatoIscrizione.RICHIESTA,
    approvata_il: datetime | None = None,
) -> Iscrizione:
    """Iscrizione già nello stato dato, senza audit (dato di partenza dei test)."""
    approvata = stato not in {StatoIscrizione.RICHIESTA, StatoIscrizione.RIFIUTATA}
    iscrizione = Iscrizione(
        persona_id=persona.id,
        edizione_id=edizione.id,
        stato=stato,
        approvata_il=(approvata_il or datetime.now(UTC)) if approvata else None,
    )
    sessione.add(iscrizione)
    sessione.flush()
    return iscrizione
