"""Job di sistema: scadenza all'inizio dell'edizione (US-17) e rete di sicurezza della
promozione (US-09). Chiamato direttamente, come lo lancia `python -m academy_hub.job`."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub import job
from academy_hub.config import impostazioni
from academy_hub.db.modelli import Edizione, EventoAudit, Iscrizione
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi
from academy_hub.repository.iscrizioni import eventi_audit

from .api import edizione, iscrizione, persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def nuova(db: Engine, edizione_id: int, stato: StatoIscrizione, minuto: int = 0) -> int:
    chi = persona(db, f"P{stato.value}{minuto}")
    return iscrizione(
        db, int(chi["X-Persona-Id"]), edizione_id, stato, T0 + timedelta(minutes=minuto)
    )


def stato(db: Engine, iscrizione_id: int) -> StatoIscrizione:
    with Session(db) as sessione:
        return sessione.get_one(Iscrizione, iscrizione_id).stato


def conta_eventi(db: Engine) -> int:
    with Session(db) as sessione:
        return sessione.scalar(select(func.count()).select_from(EventoAudit)) or 0


def con_posti_liberi(db: Engine, edizione_id: int, posti_confermati: int) -> None:
    """Stato che la promozione inline non lascia mai: posti liberi e lista d'attesa."""
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Edizione, edizione_id).posti_confermati = posti_confermati


# --- US-17 · Scadenza all'inizio dell'edizione -------------------------------------


@pytest.mark.parametrize("giorni", [0, -3])
def test_d8_all_inizio_le_iscrizioni_pendenti_diventano_annullate(db: Engine, giorni: int) -> None:
    edizione_id = edizione(db, capienza=2, inizio=oggi() + timedelta(days=giorni))
    pendenti = {s: nuova(db, edizione_id, s) for s in (S.RICHIESTA, S.APPROVATA, S.IN_ATTESA)}
    confermata = nuova(db, edizione_id, S.CONFERMATA)

    esito = job.esegui(db)

    assert esito.annullate == 3
    with Session(db) as sessione:
        for stato_iniziale, iscrizione_id in pendenti.items():
            assert sessione.get_one(Iscrizione, iscrizione_id).stato is S.ANNULLATA
            [evento] = eventi_audit(sessione, iscrizione_id)
            assert (evento.stato_da, evento.motivo, evento.autore_id) == (
                stato_iniziale,
                "edizione-iniziata",
                None,
            )
        assert sessione.get_one(Iscrizione, confermata).stato is S.CONFERMATA
        assert eventi_audit(sessione, confermata) == []
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 1


def test_le_edizioni_non_iniziate_restano_come_sono(db: Engine) -> None:
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=1))
    richiesta = nuova(db, edizione_id, S.RICHIESTA)

    esito = job.esegui(db)

    assert (esito.annullate, esito.promosse) == (0, 0)
    assert stato(db, richiesta) is S.RICHIESTA


def test_il_job_e_idempotente(db: Engine) -> None:
    edizione_id = edizione(db, inizio=oggi())
    for s in (S.RICHIESTA, S.APPROVATA, S.IN_ATTESA):
        nuova(db, edizione_id, s)
    job.esegui(db)
    eventi = conta_eventi(db)

    esito = job.esegui(db)

    assert (esito.annullate, esito.promosse) == (0, 0)
    assert conta_eventi(db) == eventi


# --- US-09 · Rete di sicurezza della promozione ------------------------------------


def test_promuove_dove_ci_sono_posti_liberi_e_lista_d_attesa(db: Engine) -> None:
    edizione_id = edizione(db, capienza=2)
    in_lista = [nuova(db, edizione_id, S.IN_ATTESA, minuto) for minuto in range(3)]
    con_posti_liberi(db, edizione_id, 0)

    esito = job.esegui(db)

    assert esito.promosse == 2
    assert [stato(db, i) for i in in_lista] == [S.CONFERMATA, S.CONFERMATA, S.IN_ATTESA]
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 2
        [evento] = eventi_audit(sessione, in_lista[0])
        assert (evento.stato_a, evento.autore_id) == (S.CONFERMATA, None)


def test_d2_a_edizione_iniziata_annulla_invece_di_promuovere(db: Engine) -> None:
    edizione_id = edizione(db, capienza=2, inizio=oggi())
    in_lista = nuova(db, edizione_id, S.IN_ATTESA)
    con_posti_liberi(db, edizione_id, 0)

    esito = job.esegui(db)

    assert (esito.annullate, esito.promosse) == (1, 0)
    assert stato(db, in_lista) is S.ANNULLATA


# --- Lancio da riga di comando -----------------------------------------------------


def test_main_esegue_una_volta_sul_database_configurato(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACADEMY_DATABASE_URL", db.url.render_as_string(hide_password=False))
    impostazioni.cache_clear()
    edizione_id = edizione(db, inizio=oggi())
    richiesta = nuova(db, edizione_id, S.RICHIESTA)

    try:
        assert job.main([]) == 0
    finally:
        impostazioni.cache_clear()

    assert stato(db, richiesta) is S.ANNULLATA


def test_ogni_deve_essere_positivo() -> None:
    with pytest.raises(SystemExit):
        job.main(["--ogni", "0"])
