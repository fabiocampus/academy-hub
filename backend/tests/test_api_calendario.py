"""Calendario dell'iscrizione confermata dietro feature flag (issue #86, ADR-0014)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.api import PREFISSO
from academy_hub.config import impostazioni
from academy_hub.db.modelli import Edizione
from academy_hub.dominio.stati import StatoIscrizione

from .api import R, edizione, iscrizione, persona

S = StatoIscrizione
pytestmark = pytest.mark.integrazione


@pytest.fixture
def flag_accesa(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ACADEMY_FLAG_CALENDARIO", "true")
    impostazioni.cache_clear()
    yield client
    impostazioni.cache_clear()


def _url(iscrizione_id: int) -> str:
    return f"{PREFISSO}/iscrizioni/{iscrizione_id}/calendario.ics"


def _confermata(db: Engine) -> tuple[dict[str, str], int, int]:
    anna = persona(db, "Anna")
    ed = edizione(db)
    return anna, ed, iscrizione(db, int(anna["X-Persona-Id"]), ed, S.CONFERMATA)


def test_titolare_scarica_l_evento(flag_accesa: TestClient, db: Engine) -> None:
    anna, ed, iscr = _confermata(db)
    with Session(db) as sessione:
        e = sessione.get_one(Edizione, ed)
        inizio, fine = e.data_inizio, e.data_fine

    risposta = flag_accesa.get(_url(iscr), headers=anna)

    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == "text/calendar; charset=utf-8"
    assert risposta.headers["content-disposition"] == (
        f'attachment; filename="iscrizione-{iscr}.ics"'
    )
    assert risposta.headers["cache-control"] == "no-store"
    corpo = risposta.text
    assert f"UID:iscrizione-{iscr}@locale.academy-hub\r\n" in corpo
    assert "SUMMARY:SQL per analisti\r\n" in corpo
    assert f"DTSTART;VALUE=DATE:{inizio:%Y%m%d}\r\n" in corpo
    # La fine è esclusa: il giorno dopo l'ultimo.
    assert f"DTEND;VALUE=DATE:{fine + timedelta(days=1):%Y%m%d}\r\n" in corpo


@pytest.mark.parametrize("stato", [S.RICHIESTA, S.APPROVATA, S.IN_ATTESA, S.ANNULLATA])
def test_solo_per_un_posto_confermato(
    flag_accesa: TestClient, db: Engine, stato: StatoIscrizione
) -> None:
    anna = persona(db, "Anna")
    iscr = iscrizione(db, int(anna["X-Persona-Id"]), edizione(db), stato)

    risposta = flag_accesa.get(_url(iscr), headers=anna)

    assert risposta.status_code == 409
    assert risposta.json()["type"] == "/problemi/iscrizione-non-confermata"


def test_solo_il_titolare(flag_accesa: TestClient, db: Engine) -> None:
    _, _, iscr = _confermata(db)
    admin = persona(db, "Alba", R.DIPENDENTE, R.ADMIN_ACADEMY)

    for estraneo in (persona(db, "Bruno"), admin):
        assert flag_accesa.get(_url(iscr), headers=estraneo).status_code == 403


def test_iscrizione_inesistente(flag_accesa: TestClient, db: Engine) -> None:
    assert flag_accesa.get(_url(999_999), headers=persona(db, "Anna")).status_code == 404


def test_flag_spenta_404_per_tutti_anche_senza_identita(client: TestClient, db: Engine) -> None:
    """La funzione spenta non esiste: 404 prima di guardare chi chiede."""
    anna, _, iscr = _confermata(db)

    for intestazioni in (anna, {}):
        risposta = client.get(_url(iscr), headers=intestazioni)
        assert risposta.status_code == 404
        assert risposta.json()["type"] == "/problemi/funzione-non-disponibile"
