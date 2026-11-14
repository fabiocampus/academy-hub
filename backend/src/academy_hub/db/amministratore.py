"""Prima persona amministratrice di un ambiente su Databricks (ADR-0010).

Su Databricks si entra con l'email dell'account, che non può stare nel repository
pubblico: arriva da `ACADEMY_ADMIN_EMAIL`, valorizzata dalla variabile del bundle al
deploy. Senza una persona con `admin_academy` nessuno potrebbe creare il catalogo.

Come `db/demo.py` è codice di bootstrap fuori dalle richieste: usa l'ORM direttamente e
non passa da `repository/`, che serve le rotte e i servizi.
"""

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Persona, Team
from academy_hub.dominio.ruoli import Ruolo

TEAM = "Academy"
RUOLI = (Ruolo.DIPENDENTE, Ruolo.ADMIN_ACADEMY)


def assicura_amministratore(motore: Engine, email: str) -> bool:
    """Crea la persona (e il team `Academy` se manca); False se l'email esiste già.

    Una persona esistente non si tocca: i ruoli si cambiano dall'applicazione, e
    riavviare l'App non deve ridare ruoli tolti.
    """
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("ACADEMY_ADMIN_EMAIL non è un'email")
    with Session(motore) as sessione, sessione.begin():
        if sessione.scalar(select(Persona.id).where(Persona.email == email)) is not None:
            return False
        team = sessione.scalar(select(Team).where(Team.nome == TEAM))
        if team is None:
            team = Team(nome=TEAM)
            sessione.add(team)
            sessione.flush()
        nome = email.partition("@")[0]
        sessione.add(
            Persona(nome=nome, email=email, team_id=team.id, ruoli=[r.value for r in RUOLI])
        )
    return True
