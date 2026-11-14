"""Elenchi della gestione Academy (issue #64): corsi, edizioni di un corso, iscrizioni di
un'edizione, docenti. Servono alle schermate dell'admin; chi può chiamarli lo verifica
la matrice di `test_autorizzazione.py`."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi

from .api import iscrizione, persona
from .dati import crea_persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
URL = "/api/v1"


def _corso(db: Engine, titolo: str, archiviato: bool = False) -> int:
    with Session(db) as sessione:
        corso = Corso(titolo=titolo, durata_ore=4)
        sessione.add(corso)
        sessione.flush()
        if archiviato:
            corso.archiviato_il = datetime.now(UTC)
        sessione.commit()
        return corso.id


def _edizione(
    db: Engine, corso_id: int, giorni: int, capienza: int = 10, cancellata: bool = False
) -> int:
    with Session(db) as sessione:
        inizio = oggi() + timedelta(days=giorni)
        edizione = Edizione(
            corso_id=corso_id,
            data_inizio=inizio,
            data_fine=inizio + timedelta(days=1),
            capienza=capienza,
            posti_confermati=0,
        )
        sessione.add(edizione)
        sessione.flush()
        if cancellata:
            edizione.cancellata_il = datetime.now(UTC)
        sessione.commit()
        return edizione.id


# --- GET /corsi --------------------------------------------------------------------


def test_elenco_corsi_attivi_prima_poi_archiviati_per_titolo(
    client: TestClient, db: Engine
) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    archiviato = _corso(db, "Analisi", archiviato=True)
    sql = _corso(db, "SQL")
    python = _corso(db, "Python")

    risposta = client.get(f"{URL}/corsi", headers=admin)

    assert risposta.status_code == 200
    pagina = risposta.json()
    assert [c["id"] for c in pagina["elementi"]] == [python, sql, archiviato]
    assert pagina["totale"] == 3
    assert pagina["elementi"][2]["archiviato_il"] is not None


def test_elenco_corsi_filtra_per_titolo_e_pagina(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    _corso(db, "SQL per analisti")
    avanzato = _corso(db, "SQL avanzato")
    _corso(db, "Python")
    _corso(db, "100% pratico")

    risposta = client.get(f"{URL}/corsi?titolo=sql&limite=1", headers=admin)
    percento = client.get(f"{URL}/corsi?titolo=%25", headers=admin)

    pagina = risposta.json()
    assert (pagina["totale"], pagina["limite"], pagina["offset"]) == (2, 1, 0)
    assert [c["id"] for c in pagina["elementi"]] == [avanzato]
    assert [c["titolo"] for c in percento.json()["elementi"]] == ["100% pratico"]


# --- GET /corsi/{id}/edizioni --------------------------------------------------------


def test_edizioni_del_corso_comprese_passate_e_cancellate(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id = _corso(db, "SQL")
    altro = _corso(db, "Python")
    futura = _edizione(db, corso_id, 30, capienza=1)
    passata = _edizione(db, corso_id, -10)
    cancellata = _edizione(db, corso_id, 60, cancellata=True)
    _edizione(db, altro, 30)
    anna, bruno = (int(persona(db, n)["X-Persona-Id"]) for n in ("Anna", "Bruno"))
    iscrizione(db, anna, futura, S.CONFERMATA)
    iscrizione(db, bruno, futura, S.IN_ATTESA)

    risposta = client.get(f"{URL}/corsi/{corso_id}/edizioni", headers=admin)

    assert risposta.status_code == 200
    pagina = risposta.json()
    assert [e["id"] for e in pagina["elementi"]] == [cancellata, futura, passata]
    assert pagina["totale"] == 3
    voce = pagina["elementi"][1]
    assert (voce["posti_confermati"], voce["lista_attesa"], voce["capienza"]) == (1, 1, 1)
    assert pagina["elementi"][0]["cancellata_il"] is not None


def test_edizioni_di_un_corso_inesistente_404(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.get(f"{URL}/corsi/999999/edizioni", headers=admin)

    assert risposta.status_code == 404
    assert risposta.json()["type"] == "/problemi/non-trovato"


# --- GET /edizioni/{id}/iscrizioni ---------------------------------------------------


def test_iscrizioni_dell_edizione_con_persona_e_posizione(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = _edizione(db, _corso(db, "SQL"), 30, capienza=1)
    altra = _edizione(db, _corso(db, "Python"), 30)
    ids = {n: int(persona(db, n)["X-Persona-Id"]) for n in ("Anna", "Bruno", "Carla", "Dario")}
    confermata = iscrizione(db, ids["Anna"], edizione_id, S.CONFERMATA)
    prima = iscrizione(db, ids["Bruno"], edizione_id, S.IN_ATTESA)
    seconda = iscrizione(db, ids["Carla"], edizione_id, S.IN_ATTESA)
    approvata = iscrizione(db, ids["Dario"], edizione_id, S.APPROVATA)
    iscrizione(db, ids["Anna"], altra, S.RICHIESTA)

    risposta = client.get(f"{URL}/edizioni/{edizione_id}/iscrizioni", headers=admin)

    assert risposta.status_code == 200
    pagina = risposta.json()
    assert pagina["totale"] == 4
    voci = {v["id"]: v for v in pagina["elementi"]}
    assert list(voci) == [confermata, prima, seconda, approvata]
    assert voci[prima]["persona"] == {"id": ids["Bruno"], "nome": "Bruno"}
    assert [voci[i]["posizione_lista_attesa"] for i in voci] == [None, 1, 2, None]
    assert voci[approvata]["stato"] == "Approvata"


def test_iscrizioni_dell_edizione_filtrate_per_stato(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = _edizione(db, _corso(db, "SQL"), 30)
    anna, bruno = (int(persona(db, n)["X-Persona-Id"]) for n in ("Anna", "Bruno"))
    iscrizione(db, anna, edizione_id, S.RICHIESTA)
    approvata = iscrizione(db, bruno, edizione_id, S.APPROVATA)

    risposta = client.get(f"{URL}/edizioni/{edizione_id}/iscrizioni?stato=Approvata", headers=admin)

    pagina = risposta.json()
    assert (pagina["totale"], [v["id"] for v in pagina["elementi"]]) == (1, [approvata])


def test_iscrizioni_di_un_edizione_inesistente_404(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.get(f"{URL}/edizioni/999999/iscrizioni", headers=admin)

    assert risposta.status_code == 404


def test_stato_sconosciuto_422(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = _edizione(db, _corso(db, "SQL"), 30)

    risposta = client.get(f"{URL}/edizioni/{edizione_id}/iscrizioni?stato=Boh", headers=admin)

    assert risposta.status_code == 422


# --- GET /docenti --------------------------------------------------------------------


def test_docenti_in_ordine_di_nome(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    with Session(db) as sessione:
        zeno = crea_persona(sessione, "Zeno", ruoli=(Ruolo.DOCENTE,))
        dora = crea_persona(sessione, "Dora", ruoli=(Ruolo.DIPENDENTE, Ruolo.DOCENTE))
        crea_persona(sessione, "Anna")
        sessione.commit()
        attesi = [{"id": dora.id, "nome": "Dora"}, {"id": zeno.id, "nome": "Zeno"}]

    risposta = client.get(f"{URL}/docenti", headers=admin)

    assert risposta.status_code == 200
    assert risposta.json() == attesi
