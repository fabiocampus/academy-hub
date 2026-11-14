"""Dati sintetici per i test di integrazione. Nessun dato reale: domini `.test` (RFC 2606)."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione, Iscrizione, Persona, Team
from academy_hub.dominio.stati import StatoIscrizione


def crea_persona(sessione: Session, nome: str, team: Team | None = None) -> Persona:
    if team is None:
        team = Team(nome=f"Team di {nome}")
        sessione.add(team)
        sessione.flush()
    persona = Persona(nome=nome, email=f"{nome.lower()}@esempio.test", team_id=team.id)
    sessione.add(persona)
    sessione.flush()
    return persona


def crea_edizione(sessione: Session, capienza: int = 10, posti_confermati: int = 0) -> Edizione:
    corso = Corso(titolo="SQL per analisti", durata_ore=8)
    sessione.add(corso)
    sessione.flush()
    inizio = date.today() + timedelta(days=30)
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
) -> Iscrizione:
    approvata = stato not in {StatoIscrizione.RICHIESTA, StatoIscrizione.RIFIUTATA}
    iscrizione = Iscrizione(
        persona_id=persona.id,
        edizione_id=edizione.id,
        stato=stato,
        approvata_il=datetime.now(UTC) if approvata else None,
    )
    sessione.add(iscrizione)
    sessione.flush()
    return iscrizione
