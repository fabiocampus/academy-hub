"""Dati demo per l'ambiente locale: le persone degli utenti del realm Keycloak (ADR-0008).

```bash
python -m academy_hub.db.demo   # dopo le migrazioni; non fa nulla se i dati ci sono già
```

Le email coincidono con quelle di `keycloak/realm-academy.json` (lo verifica un test):
chi accede con un utente di prova diventa la persona con la stessa email, con i ruoli
scritti qui. Solo dati sintetici, e solo con `ACADEMY_AMBIENTE=locale`.

```
Direzione (resp. Diana Dirigente)
├── Dati    (resp. Rita Responsabile): Dario Dipendente
└── Academy (resp. Diana Dirigente):   Alba Admin, Dora Docente
```
"""

import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from academy_hub.config import impostazioni
from academy_hub.db.modelli import Corso, Edizione, Persona, Team
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.tempo import oggi

log = logging.getLogger("academy_hub.db.demo")

DOMINIO = "academy.example"


@dataclass(frozen=True)
class PersonaDemo:
    utente: str
    nome: str
    team: str
    ruoli: tuple[Ruolo, ...]

    @property
    def email(self) -> str:
        return f"{self.utente}@{DOMINIO}"


R = Ruolo
PERSONE = (
    PersonaDemo("dirigente", "Diana Dirigente", "Direzione", (R.DIPENDENTE, R.RESPONSABILE)),
    PersonaDemo("responsabile", "Rita Responsabile", "Dati", (R.DIPENDENTE, R.RESPONSABILE)),
    PersonaDemo("dipendente", "Dario Dipendente", "Dati", (R.DIPENDENTE,)),
    PersonaDemo("admin", "Alba Admin", "Academy", (R.DIPENDENTE, R.ADMIN_ACADEMY)),
    PersonaDemo("docente", "Dora Docente", "Academy", (R.DIPENDENTE, R.DOCENTE)),
)
# team: (padre, utente del responsabile)
TEAM = {
    "Direzione": (None, "dirigente"),
    "Dati": ("Direzione", "responsabile"),
    "Academy": ("Direzione", "dirigente"),
}
UTENTI_SENZA_PERSONA = ("esterna",)
"""Utenti del realm senza persona: mostrano il 403 persona-non-registrata."""


def carica(motore: Engine, da: date | None = None) -> bool:
    """Inserisce i dati demo; False se c'erano già (si riconoscono dalle email)."""
    inizio = da or oggi()
    with Session(motore) as sessione, sessione.begin():
        if sessione.scalar(select(Persona.id).where(Persona.email == PERSONE[0].email)):
            return False
        team: dict[str, Team] = {}
        for nome, (padre, _) in TEAM.items():
            team[nome] = Team(nome=nome, team_padre_id=padre and team[padre].id)
            sessione.add(team[nome])
            sessione.flush()
        persone: dict[str, Persona] = {}
        for p in PERSONE:
            persone[p.utente] = Persona(
                nome=p.nome,
                email=p.email,
                team_id=team[p.team].id,
                ruoli=[r.value for r in p.ruoli],
            )
            sessione.add(persone[p.utente])
        sessione.flush()
        for nome, (_, responsabile) in TEAM.items():
            team[nome].responsabile_id = persone[responsabile].id
        _catalogo(sessione, inizio, persone["docente"].id)
    return True


def _catalogo(sessione: Session, inizio: date, docente_id: int) -> None:
    python = Corso(
        titolo="Python per l'analisi dei dati", descrizione="Pandas e notebook.", durata_ore=16
    )
    sql = Corso(
        titolo="SQL avanzato", descrizione="Finestre, CTE, piani di esecuzione.", durata_ore=8
    )
    sessione.add_all([python, sql])
    sessione.flush()
    sessione.add_all(
        [
            _edizione(python, inizio + timedelta(days=21), 2, 10, docente_id),
            _edizione(python, inizio + timedelta(days=60), 2, 10, docente_id),
            # Un posto solo: per provare la lista d'attesa (US-09).
            _edizione(sql, inizio + timedelta(days=30), 1, 1, None),
        ]
    )


def _edizione(
    corso: Corso, inizio: date, giorni: int, capienza: int, docente: int | None
) -> Edizione:
    return Edizione(
        corso_id=corso.id,
        data_inizio=inizio,
        data_fine=inizio + timedelta(days=giorni - 1),
        capienza=capienza,
        docente_id=docente,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = impostazioni()
    if config.ambiente != "locale":
        # Esce senza errore: il servizio demo di compose non deve fermare il backend.
        log.warning("Dati demo solo con ACADEMY_AMBIENTE=locale (ora %s): salto", config.ambiente)
        return 0
    caricati = carica(create_engine(config.database_url))
    log.info("Dati demo %s", "caricati" if caricati else "già presenti: nessuna modifica")
    return 0


if __name__ == "__main__":
    sys.exit(main())
