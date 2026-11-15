"""Dati di prova sintetici del collaudo (issue #86)."""

from datetime import date

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.config import Impostazioni
from academy_hub.db import dati_prova
from academy_hub.db.modelli import Edizione, EventoAudit, Iscrizione, Persona
from academy_hub.dominio.stati import StatoIscrizione

S = StatoIscrizione
DA = date(2026, 11, 16)


@pytest.mark.integrazione
def test_carica_una_volta_sola(db: Engine) -> None:
    primo = dati_prova.carica(db, DA)

    assert primo is not None
    assert dati_prova.carica(db, DA) is None
    with Session(db) as sessione:
        assert sessione.scalar(select(func.count()).select_from(Persona)) == primo.persone


@pytest.mark.integrazione
def test_deterministico_e_vario(db: Engine) -> None:
    riepilogo = dati_prova.carica(db, DA)

    assert riepilogo is not None
    assert riepilogo.persone == 3 + len(dati_prova.TEAM) * (1 + dati_prova.DIPENDENTI_PER_TEAM)
    assert riepilogo.edizioni == 2 * len(dati_prova.CORSI)
    # Ogni stato che il flusso produce prima dell'inizio dell'edizione.
    assert set(riepilogo.iscrizioni) == {
        S.RICHIESTA,
        S.APPROVATA,
        S.RIFIUTATA,
        S.ANNULLATA,
        S.CONFERMATA,
        S.IN_ATTESA,
    }


@pytest.mark.integrazione
def test_solo_dati_sintetici_coerenti(db: Engine) -> None:
    dati_prova.carica(db, DA)

    with Session(db) as sessione:
        email = sessione.scalars(select(Persona.email)).all()
        assert all(e.endswith("@academy.example") for e in email)
        assert len(set(email)) == len(email)
        for edizione in sessione.scalars(select(Edizione)):
            confermate = sessione.execute(
                select(func.count())
                .select_from(Iscrizione)
                .where(Iscrizione.edizione_id == edizione.id, Iscrizione.stato == S.CONFERMATA)
            ).scalar_one()
            assert edizione.posti_confermati == confermate <= edizione.capienza
        # Passate dai servizi: ogni iscrizione ha la sua storia, a partire dalla richiesta.
        senza_storia = sessione.scalar(
            select(func.count())
            .select_from(Iscrizione)
            .where(
                ~select(EventoAudit.id).where(EventoAudit.iscrizione_id == Iscrizione.id).exists()
            )
        )
        assert senza_storia == 0


def test_vietati_in_produzione() -> None:
    with pytest.raises(ValueError, match="ACADEMY_DATI_PROVA non è ammessa in produzione"):
        Impostazioni(ambiente="produzione", identita="databricks", dati_prova=True)


def test_ammessi_in_collaudo() -> None:
    assert Impostazioni(ambiente="collaudo", identita="databricks", dati_prova=True).dati_prova
