"""Promozione e cancellazione con transazioni simultanee (US-09, US-18; R3, R4)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Iscrizione
from academy_hub.dominio.errori import EdizioneCancellata
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import STATI_ATTIVI, StatoIscrizione
from academy_hub.servizi import catalogo, iscrizioni

from .api import edizione, iscrizione, organigramma, persona
from .concorrenza import attore, insieme

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def nuova(db: Engine, nome: str, edizione_id: int, stato: StatoIscrizione, minuto: int = 0) -> int:
    persona_id = int(persona(db, nome)["X-Persona-Id"])
    return iscrizione(db, persona_id, edizione_id, stato, T0 + timedelta(minutes=minuto))


def titolare(db: Engine, iscrizione_id: int) -> int:
    with Session(db) as sessione:
        return sessione.get_one(Iscrizione, iscrizione_id).persona_id


def stati(db: Engine, ids: list[int]) -> list[StatoIscrizione]:
    with Session(db) as sessione:
        return [sessione.get_one(Iscrizione, i).stato for i in ids]


def posti(db: Engine, edizione_id: int) -> int:
    with Session(db) as sessione:
        return sessione.get_one(Edizione, edizione_id).posti_confermati


def test_r4_annullamenti_simultanei_promuovono_in_ordine(db: Engine) -> None:
    edizione_id = edizione(db, capienza=2)
    confermate = [nuova(db, f"C{n}", edizione_id, S.CONFERMATA) for n in range(2)]
    in_lista = [nuova(db, f"L{n}", edizione_id, S.IN_ATTESA, n) for n in range(3)]
    titolari = [attore(db, titolare(db, i)) for i in confermate]

    esiti = insieme(
        db,
        [
            lambda s, chi=chi, i=i: iscrizioni.annulla(s, chi, i, 3).stato
            for chi, i in zip(titolari, confermate, strict=True)
        ],
    )

    assert esiti == [S.ANNULLATA, S.ANNULLATA]
    assert stati(db, in_lista) == [S.CONFERMATA, S.CONFERMATA, S.IN_ATTESA]
    assert posti(db, edizione_id) == 2


def test_r4_annullamento_e_conferma_simultanei_il_posto_va_alla_lista(db: Engine) -> None:
    edizione_id = edizione(db, capienza=1)
    confermata = nuova(db, "Anna", edizione_id, S.CONFERMATA)
    in_lista = nuova(db, "Bruno", edizione_id, S.IN_ATTESA)
    approvata = iscrizione(db, int(persona(db, "Carla")["X-Persona-Id"]), edizione_id, S.APPROVATA)
    anna = attore(db, titolare(db, confermata))
    admin = attore(db, int(persona(db, "Admin", Ruolo.ADMIN_ACADEMY)["X-Persona-Id"]))

    insieme(
        db,
        [
            lambda s: iscrizioni.annulla(s, anna, confermata, 3).stato,
            lambda s: iscrizioni.conferma_posto(s, admin, approvata).stato,
        ],
    )

    assert stati(db, [in_lista, approvata]) == [S.CONFERMATA, S.IN_ATTESA]
    assert posti(db, edizione_id) == 1


@pytest.mark.parametrize("decisione", ["approva", "rifiuta"])
def test_d10_cancellazione_e_decisione_simultanee_nessuna_iscrizione_resta_attiva(
    db: Engine, decisione: str
) -> None:
    """La decisione blocca solo l'iscrizione: la cancellazione la aspetta e ricontrolla lo
    stato (READ COMMITTED). Approvata → annullata; Rifiutata → saltata."""
    org = organigramma(db)
    edizione_id = edizione(db)
    richiesta = iscrizione(db, org.ids["Anna"], edizione_id, S.RICHIESTA)
    rossa, admin = attore(db, org.ids["Rossa"]), attore(db, org.ids["Admin"])

    def decidi(s: Session) -> StatoIscrizione:
        if decisione == "approva":
            return iscrizioni.approva(s, rossa, richiesta).stato
        return iscrizioni.rifiuta(s, rossa, richiesta, "Budget").stato

    insieme(db, [lambda s: catalogo.cancella_edizione(s, admin, edizione_id).id, decidi])

    with Session(db) as sessione:
        finale = sessione.get_one(Iscrizione, richiesta).stato
        assert finale in {S.ANNULLATA, S.RIFIUTATA}
        assert sessione.get_one(Edizione, edizione_id).cancellata_il is not None
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 0


def test_d10_cancellazione_e_richiesta_simultanee_nessuna_iscrizione_resta_attiva(
    db: Engine,
) -> None:
    edizione_id = edizione(db)
    anna = attore(db, int(persona(db, "Anna")["X-Persona-Id"]))
    admin = attore(db, int(persona(db, "Admin", Ruolo.ADMIN_ACADEMY)["X-Persona-Id"]))

    esiti = insieme(
        db,
        [
            lambda s: catalogo.cancella_edizione(s, admin, edizione_id).id,
            lambda s: iscrizioni.richiedi_iscrizione(s, anna, edizione_id).id,
        ],
    )

    assert esiti[0] == edizione_id
    assert isinstance(esiti[1], (int, EdizioneCancellata)), esiti
    with Session(db) as sessione:
        attive = sessione.scalars(
            select(Iscrizione).where(
                Iscrizione.edizione_id == edizione_id, Iscrizione.stato.in_(STATI_ATTIVI)
            )
        ).all()
        assert attive == []
        assert sessione.get_one(Edizione, edizione_id).cancellata_il is not None
