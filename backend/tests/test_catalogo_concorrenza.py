"""US-01/US-02: un'edizione non nasce su un corso che un'altra transazione sta archiviando."""

from datetime import timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.tempo import oggi
from academy_hub.servizi import catalogo

from .dati import crea_persona

pytestmark = pytest.mark.integrazione


def prepara(db: Engine) -> tuple[Attore, int]:
    with Session(db) as sessione, sessione.begin():
        admin = crea_persona(sessione, "Admin", ruoli=(Ruolo.ADMIN_ACADEMY,))
        corso = Corso(titolo="SQL per analisti", durata_ore=8)
        sessione.add(corso)
        sessione.flush()
        return Attore(admin.id, admin.team_id, frozenset({Ruolo.ADMIN_ACADEMY})), corso.id


def test_archiviazione_attende_la_creazione_di_un_edizione(db: Engine) -> None:
    """`crea_edizione` legge il corso con FOR SHARE: l'archiviazione deve aspettarne la fine.

    Senza il lock la seconda transazione archivierebbe subito e la prima creerebbe
    un'edizione di un corso archiviato.
    """
    admin, corso_id = prepara(db)
    inizio = oggi() + timedelta(days=30)

    with Session(db) as prima, prima.begin():
        catalogo.crea_edizione(prima, admin, corso_id, inizio, inizio, capienza=10)

        with Session(db) as seconda, seconda.begin():
            seconda.execute(text("SET LOCAL lock_timeout = '300ms'"))
            versione = seconda.get_one(Corso, corso_id).versione
            with pytest.raises(OperationalError, match="lock timeout"):
                catalogo.archivia_corso(seconda, admin, corso_id, versione)
