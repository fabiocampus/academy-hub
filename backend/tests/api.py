"""Aiuti per i test dell'API HTTP."""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Persona
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione

from .dati import crea_edizione, crea_iscrizione, crea_persona, crea_team

R = Ruolo


def persona(db: Engine, nome: str, *ruoli: Ruolo) -> dict[str, str]:
    """Header d'identità di una persona nuova con i ruoli dati."""
    with Session(db) as sessione:
        p = crea_persona(sessione, nome, ruoli=ruoli or (Ruolo.DIPENDENTE,))
        sessione.commit()
        return {"X-Persona-Id": str(p.id)}


def edizione(db: Engine, capienza: int = 10, inizio: date | None = None) -> int:
    with Session(db) as sessione:
        creata = crea_edizione(sessione, capienza=capienza, inizio=inizio)
        sessione.commit()
        return creata.id


def iscrizione(
    db: Engine,
    persona_id: int,
    edizione_id: int,
    stato: StatoIscrizione,
    approvata_il: datetime | None = None,
) -> int:
    """Iscrizione già nello stato dato (senza audit); se Confermata, occupa un posto."""
    with Session(db) as sessione:
        ed = sessione.get_one(Edizione, edizione_id)
        if stato is StatoIscrizione.CONFERMATA:
            ed.posti_confermati += 1
        creata = crea_iscrizione(
            sessione, sessione.get_one(Persona, persona_id), ed, stato, approvata_il
        )
        sessione.commit()
        return creata.id


@dataclass
class Organigramma:
    """Organigramma sintetico dei test di approvazione.

    ```
    Vertice (resp. Dirigente; c'è anche Admin)
    ├── Dati (resp. Rossa): Anna, Bruno
    └── Web  (resp. Verdi): Carla
    ```
    """

    ids: dict[str, int] = field(default_factory=dict[str, int])
    team: dict[str, int] = field(default_factory=dict[str, int])

    def __call__(self, nome: str) -> dict[str, str]:
        """Header d'identità della persona."""
        return {"X-Persona-Id": str(self.ids[nome])}


def organigramma(db: Engine) -> Organigramma:
    org = Organigramma()
    with Session(db) as sessione:
        vertice = crea_team(sessione, "Vertice")
        dati = crea_team(sessione, "Dati", vertice)
        web = crea_team(sessione, "Web", vertice)
        persone = {
            "Dirigente": (vertice, (R.DIPENDENTE, R.RESPONSABILE)),
            "Admin": (vertice, (R.DIPENDENTE, R.ADMIN_ACADEMY)),
            "Rossa": (dati, (R.DIPENDENTE, R.RESPONSABILE)),
            "Anna": (dati, (R.DIPENDENTE,)),
            "Bruno": (dati, (R.DIPENDENTE,)),
            "Verdi": (web, (R.DIPENDENTE, R.RESPONSABILE)),
            "Carla": (web, (R.DIPENDENTE,)),
        }
        for nome, (team, ruoli) in persone.items():
            org.ids[nome] = crea_persona(sessione, nome, team, ruoli).id
        vertice.responsabile_id = org.ids["Dirigente"]
        dati.responsabile_id = org.ids["Rossa"]
        web.responsabile_id = org.ids["Verdi"]
        org.team = {"Vertice": vertice.id, "Dati": dati.id, "Web": web.id}
        sessione.commit()
    return org
