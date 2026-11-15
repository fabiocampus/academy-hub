"""Dati di prova sintetici per il collaudo (fase 10, issue #86): mai dati reali.

```bash
ACADEMY_DATI_PROVA=true python -m academy_hub.avvio   # su Databricks: variabile del bundle
python -m academy_hub.db.dati_prova                     # a mano, dopo le migrazioni
```

Generatore deterministico (seme fisso): stessi team, persone, corsi, edizioni e
iscrizioni a ogni ambiente nuovo. Le persone hanno email `@academy.example` (`.example`
è riservato dall'RFC 2606): nessuno entra con queste identità, servono
a dare volume a elenchi, approvazioni e report. L'amministratore vero dell'ambiente resta
quello di `ACADEMY_ADMIN_EMAIL` (`db/amministratore.py`).

Struttura e catalogo si scrivono con l'ORM, come `db/demo.py`; le iscrizioni invece passano
dai servizi (richiesta, approvazione, rifiuto, conferma, annullamento), così hanno audit,
posti contati e lista d'attesa come quelle vere. Tutto in una transazione: o ci sono tutti
i dati di prova o nessuno. Una seconda esecuzione non fa nulla (si riconosce dal team
di vertice).

Vietato in produzione: lo impedisce la configurazione (`ACADEMY_DATI_PROVA`).
"""

import logging
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from academy_hub.config import impostazioni
from academy_hub.db.modelli import Corso, Edizione, Iscrizione, Persona, Team
from academy_hub.db.motore import crea_motore
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi
from academy_hub.servizi import iscrizioni

log = logging.getLogger("academy_hub.db.dati_prova")

DOMINIO = "academy.example"
SEME = 2026
R = Ruolo

# Il vertice e i team sotto: nomi diversi da quelli di db/demo.py e db/amministratore.py.
VERTICE = "Direzione generale"
TEAM = ("Analisi dati", "Vendite", "Risorse umane", "Tecnologia")
DIPENDENTI_PER_TEAM = 5
NOMI = (
    "Ada", "Bruno", "Carla", "Dario", "Elena", "Fabio", "Giulia", "Luca", "Marta", "Nicola",
    "Olga", "Paolo", "Rita", "Sergio", "Tina", "Ugo", "Vera", "Walter", "Zoe", "Ivo",
)  # fmt: skip
COGNOMI = (
    "Rossi", "Bianchi", "Verdi", "Neri", "Gallo", "Costa", "Fontana", "Greco", "Marino",
    "Conti", "Ferrari", "Esposito", "Romano", "Colombo", "Ricci", "Bruno",
)  # fmt: skip
CORSI = (
    ("Python per l'analisi dei dati", "Pandas, notebook e grafici.", 16),
    ("SQL avanzato", "Finestre, CTE, piani di esecuzione.", 8),
    ("Comunicare con i dati", "Raccontare un'analisi a chi decide.", 4),
    ("Sicurezza delle informazioni", "Phishing, password, dati personali.", 4),
    ("Negoziazione", "Preparare e condurre una trattativa.", 12),
    ("Git e revisione del codice", "Rami, pull request, revisioni utili.", 8),
)
# Esiti a turno delle richieste: più conferme che altro, come in un catalogo vero.
ESITI = ("confermata", "richiesta", "approvata", "confermata", "rifiutata", "annullata")
MOTIVI_RIFIUTO = ("Periodo di chiusura del trimestre", "Corso non pertinente al ruolo")


@dataclass(frozen=True)
class Riepilogo:
    persone: int
    corsi: int
    edizioni: int
    iscrizioni: Counter[StatoIscrizione]


def _attore(persona: Persona) -> Attore:
    return Attore(persona.id, persona.team_id, frozenset(Ruolo(r) for r in persona.ruoli))


class _Generatore:
    def __init__(self, sessione: Session, inizio: date) -> None:
        self.sessione = sessione
        self.inizio = inizio
        self.caso = random.Random(SEME)  # noqa: S311 - dati di prova, non crittografia
        self.usate: set[str] = set()

    def persona(self, team: Team, ruoli: tuple[Ruolo, ...]) -> Persona:
        while True:
            nome, cognome = self.caso.choice(NOMI), self.caso.choice(COGNOMI)
            utente = f"{nome}.{cognome}".lower()
            if utente not in self.usate:
                break
        self.usate.add(utente)
        persona = Persona(
            nome=f"{nome} {cognome}",
            email=f"{utente}@{DOMINIO}",
            team_id=team.id,
            ruoli=[r.value for r in ruoli],
        )
        self.sessione.add(persona)
        self.sessione.flush()
        return persona

    def team(self, nome: str, padre: Team | None) -> Team:
        team = Team(nome=nome, team_padre_id=padre and padre.id)
        self.sessione.add(team)
        self.sessione.flush()
        return team

    def edizioni(self, docente: Persona) -> list[Edizione]:
        create: list[Edizione] = []
        for titolo, descrizione, ore in CORSI:
            corso = Corso(titolo=titolo, descrizione=descrizione, durata_ore=ore)
            self.sessione.add(corso)
            self.sessione.flush()
            for _ in range(2):
                inizio = self.inizio + timedelta(days=self.caso.randint(14, 120))
                giorni = max(1, ore // 8)
                edizione = Edizione(
                    corso_id=corso.id,
                    data_inizio=inizio,
                    data_fine=inizio + timedelta(days=giorni - 1),
                    # Qualche edizione piccola, per avere una lista d'attesa (US-09).
                    capienza=self.caso.choice((2, 3, 8, 12)),
                    docente_id=docente.id if self.caso.random() < 0.5 else None,
                )
                self.sessione.add(edizione)
                create.append(edizione)
        self.sessione.flush()
        return create

    def iscrizioni(
        self,
        dipendenti: list[tuple[Persona, Persona]],
        edizioni: list[Edizione],
        admin: Persona,
    ) -> None:
        """Per ogni dipendente qualche richiesta, con esiti a turno: ogni stato c'è sempre.

        Decide il responsabile del team, conferma l'amministratore. La prima edizione ha due
        posti e la chiede il primo dipendente di ogni team: due confermati, gli altri in
        lista d'attesa (US-09).
        """
        piena, *altre = edizioni
        piena.capienza = 2
        a = _attore(admin)
        turno = 0
        for indice, (dipendente, responsabile) in enumerate(dipendenti):
            scelte = self.caso.sample(altre, self.caso.randint(1, 3))
            if indice % DIPENDENTI_PER_TEAM == 0:
                scelte = [piena, *scelte]
            for edizione in scelte:
                esito = "confermata" if edizione is piena else ESITI[turno % len(ESITI)]
                turno += edizione is not piena
                self._esito(_attore(dipendente), _attore(responsabile), a, edizione, esito)

    def _esito(
        self, titolare: Attore, decisore: Attore, admin: Attore, edizione: Edizione, esito: str
    ) -> None:
        s = self.sessione
        nuova = iscrizioni.richiedi_iscrizione(s, titolare, edizione.id)
        match esito:
            case "richiesta":
                pass
            case "rifiutata":
                iscrizioni.rifiuta(s, decisore, nuova.id, self.caso.choice(MOTIVI_RIFIUTO))
            case "annullata":
                iscrizioni.annulla(s, titolare, nuova.id, scadenza_giorni=0)
            case "approvata":
                iscrizioni.approva(s, decisore, nuova.id)
            case _:
                iscrizioni.approva(s, decisore, nuova.id)
                # Confermata se c'è posto, altrimenti in lista d'attesa (R3).
                iscrizioni.conferma_posto(s, admin, nuova.id)


def carica(motore: Engine, da: date | None = None) -> Riepilogo | None:
    """Inserisce i dati di prova; None se c'erano già."""
    with Session(motore) as sessione, sessione.begin():
        if sessione.scalar(select(Team.id).where(Team.nome == VERTICE)) is not None:
            return None
        g = _Generatore(sessione, da or oggi())
        vertice = g.team(VERTICE, None)
        dirigente = g.persona(vertice, (R.DIPENDENTE, R.RESPONSABILE))
        vertice.responsabile_id = dirigente.id
        admin = g.persona(vertice, (R.DIPENDENTE, R.ADMIN_ACADEMY))
        docente = g.persona(vertice, (R.DIPENDENTE, R.DOCENTE))
        dipendenti: list[tuple[Persona, Persona]] = []
        for nome in TEAM:
            team = g.team(nome, vertice)
            responsabile = g.persona(team, (R.DIPENDENTE, R.RESPONSABILE))
            team.responsabile_id = responsabile.id
            dipendenti += [
                (g.persona(team, (R.DIPENDENTE,)), responsabile) for _ in range(DIPENDENTI_PER_TEAM)
            ]
        sessione.flush()
        edizioni = g.edizioni(docente)
        g.iscrizioni(dipendenti, edizioni, admin)
        sessione.flush()
        stati = Counter(
            StatoIscrizione(stato)
            for stato in sessione.scalars(
                select(Iscrizione.stato)
                .join(Persona, Iscrizione.persona_id == Persona.id)
                .where(Persona.email.like(f"%@{DOMINIO}"))
            )
        )
        return Riepilogo(
            persone=len(g.usate), corsi=len(CORSI), edizioni=len(edizioni), iscrizioni=stati
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = impostazioni()
    if config.ambiente == "produzione":
        log.error("Dati di prova vietati in produzione")
        return 1
    riepilogo = carica(crea_motore(config))
    if riepilogo is None:
        log.info("Dati di prova già presenti: nessuna modifica")
    else:
        log.info("Dati di prova caricati: %s", riepilogo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
