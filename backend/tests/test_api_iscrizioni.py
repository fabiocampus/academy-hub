"""US-04 · Chiedere l'iscrizione, US-05 · Vedere le mie iscrizioni, US-10 · Annullare,
US-11 · Audit, attraverso l'API."""

from datetime import UTC, datetime, timedelta

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.config import impostazioni
from academy_hub.db.modelli import Edizione, Iscrizione
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi

from .api import edizione, iscrizione, organigramma, persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
URL = "/api/v1/iscrizioni"


def richiedi(
    client: TestClient, chi: dict[str, str], edizione_id: int, chiave: str | None = None
) -> httpx.Response:
    headers = chi if chiave is None else {**chi, "Idempotency-Key": chiave}
    return client.post(URL, json={"edizione_id": edizione_id}, headers=headers)


def tipo(risposta: httpx.Response) -> str:
    assert risposta.headers["content-type"] == "application/problem+json"
    return risposta.json()["type"]


def conta_iscrizioni(db: Engine) -> int:
    with Session(db) as sessione:
        return sessione.scalar(select(func.count()).select_from(Iscrizione)) or 0


def posti_confermati(db: Engine, edizione_id: int) -> int:
    with Session(db) as sessione:
        return sessione.get_one(Edizione, edizione_id).posti_confermati


# --- US-04 · Chiedere l'iscrizione -------------------------------------------------


def test_la_richiesta_crea_un_iscrizione_richiesta_con_audit(
    client: TestClient, db: Engine
) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db)

    risposta = richiedi(client, anna, edizione_id)

    assert risposta.status_code == 201
    creata = risposta.json()
    assert (creata["edizione_id"], creata["stato"]) == (edizione_id, "Richiesta")
    assert creata["persona_id"] == int(anna["X-Persona-Id"])
    assert creata["approvata_il"] is None
    assert risposta.headers["Location"] == f"{URL}/{creata['id']}"
    letta = client.get(f"{URL}/{creata['id']}", headers=anna).json()
    [evento] = letta["storia"]
    assert (evento["stato_da"], evento["stato_a"], evento["autore_id"]) == (
        None,
        "Richiesta",
        creata["persona_id"],
    )


def test_r1_una_seconda_richiesta_attiva_e_duplicata(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db)
    richiedi(client, anna, edizione_id)

    risposta = richiedi(client, anna, edizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/iscrizione-duplicata"
    assert conta_iscrizioni(db) == 1


def test_stessa_chiave_di_idempotenza_stessa_risposta(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db)
    chiave = "3f1c2a9e-5b7d-4c11-9a0e-7d2b6f4e8a10"

    prima = richiedi(client, anna, edizione_id, chiave)
    seconda = richiedi(client, anna, edizione_id, chiave)

    assert (prima.status_code, seconda.status_code) == (201, 201)
    assert seconda.json() == prima.json()
    assert seconda.headers["Location"] == prima.headers["Location"]
    assert conta_iscrizioni(db) == 1


def test_la_chiave_vale_per_persona(client: TestClient, db: Engine) -> None:
    edizione_id = edizione(db)

    anna = richiedi(client, persona(db, "Anna"), edizione_id, "chiave-1")
    bruno = richiedi(client, persona(db, "Bruno"), edizione_id, "chiave-1")

    assert (anna.status_code, bruno.status_code) == (201, 201)
    assert anna.json()["id"] != bruno.json()["id"]


def test_la_chiave_riusata_su_un_altra_edizione_e_422(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    richiedi(client, anna, edizione(db), "chiave-1")

    risposta = richiedi(client, anna, edizione(db), "chiave-1")

    assert risposta.status_code == 422
    assert tipo(risposta) == "/problemi/chiave-idempotenza-riusata"
    assert conta_iscrizioni(db) == 1


@pytest.mark.parametrize("chiave", ["", "x" * 65, "con spazio", "concontrollo"])
def test_chiave_di_idempotenza_malformata_422(client: TestClient, db: Engine, chiave: str) -> None:
    risposta = richiedi(client, persona(db, "Anna"), edizione(db), chiave)

    assert risposta.status_code == 422
    assert conta_iscrizioni(db) == 0


@pytest.mark.parametrize("giorni", [0, -1, -30])
def test_edizione_gia_iniziata_409(client: TestClient, db: Engine, giorni: int) -> None:
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=giorni))

    risposta = richiedi(client, persona(db, "Anna"), edizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-iniziata"


def test_edizione_cancellata_409(client: TestClient, db: Engine) -> None:
    edizione_id = edizione(db)
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Edizione, edizione_id).cancellata_il = datetime.now(UTC)

    risposta = richiedi(client, persona(db, "Anna"), edizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-cancellata"


def test_edizione_inesistente_422(client: TestClient, db: Engine) -> None:
    risposta = richiedi(client, persona(db, "Anna"), 999)

    assert risposta.status_code == 422
    assert risposta.json()["errori"][0]["campo"] == "edizione_id"


@pytest.mark.parametrize("stato", [S.RIFIUTATA, S.ANNULLATA])
def test_d4_dopo_rifiuto_o_annullamento_si_chiede_di_nuovo(
    client: TestClient, db: Engine, stato: StatoIscrizione
) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db)
    vecchia = iscrizione(db, int(anna["X-Persona-Id"]), edizione_id, stato)

    risposta = richiedi(client, anna, edizione_id)

    assert risposta.status_code == 201
    assert risposta.json()["id"] != vecchia


def test_serve_il_ruolo_dipendente(client: TestClient, db: Engine) -> None:
    solo_admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    assert richiedi(client, solo_admin, edizione(db)).status_code == 403


def test_senza_identita_401(client: TestClient, db: Engine) -> None:
    assert richiedi(client, {}, edizione(db)).status_code == 401


# --- US-05 · Vedere le mie iscrizioni ----------------------------------------------


def test_vedo_solo_le_mie_iscrizioni(client: TestClient, db: Engine) -> None:
    anna, bruno = persona(db, "Anna"), persona(db, "Bruno")
    prima, seconda = edizione(db), edizione(db)
    richiedi(client, anna, prima)
    richiedi(client, anna, seconda)
    richiedi(client, bruno, prima)

    pagina = client.get(URL, headers=anna).json()

    assert pagina["totale"] == 2
    assert {v["edizione_id"] for v in pagina["elementi"]} == {prima, seconda}
    voce = pagina["elementi"][0]
    assert voce["stato"] == "Richiesta"
    assert voce["corso"]["titolo"] == "SQL per analisti"
    assert {"data_inizio", "data_fine", "aggiornata_il"} <= voce.keys()
    assert voce["posizione_lista_attesa"] is None


def test_le_mie_iscrizioni_sono_paginate(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    for _ in range(3):
        richiedi(client, anna, edizione(db))

    pagina = client.get(URL, params={"limite": 2, "offset": 2}, headers=anna).json()

    assert (pagina["totale"], len(pagina["elementi"]), pagina["limite"]) == (3, 1, 2)


def test_in_lista_d_attesa_vedo_la_mia_posizione(client: TestClient, db: Engine) -> None:
    edizione_id = edizione(db, capienza=1)
    adesso = datetime.now(UTC)
    # Approvate in quest'ordine: Carla, Anna, Bruno. Anna è seconda.
    chi = {nome: persona(db, nome) for nome in ("Carla", "Anna", "Bruno")}
    for nome, minuti in (("Carla", 3), ("Anna", 2), ("Bruno", 1)):
        iscrizione(
            db,
            int(chi[nome]["X-Persona-Id"]),
            edizione_id,
            S.IN_ATTESA,
            approvata_il=adesso - timedelta(minutes=minuti),
        )

    [voce] = client.get(URL, headers=chi["Anna"]).json()["elementi"]

    assert (voce["stato"], voce["posizione_lista_attesa"]) == ("InAttesa", 2)


def test_la_storia_la_vedono_il_titolare_e_l_amministratore(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    creata = richiedi(client, anna, edizione(db)).json()
    percorso = f"{URL}/{creata['id']}"

    assert client.get(percorso, headers=anna).status_code == 200
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    assert client.get(percorso, headers=admin).status_code == 200
    altro = client.get(percorso, headers=persona(db, "Bruno"))
    assert altro.status_code == 403


def test_iscrizione_inesistente_404(client: TestClient, db: Engine) -> None:
    assert client.get(f"{URL}/999", headers=persona(db, "Anna")).status_code == 404


# --- US-10 · Annullare la propria iscrizione ---------------------------------------


def annulla(client: TestClient, chi: dict[str, str], iscrizione_id: int) -> httpx.Response:
    return client.post(f"{URL}/{iscrizione_id}/annullamento", headers=chi)


@pytest.mark.parametrize("stato", [S.RICHIESTA, S.APPROVATA, S.IN_ATTESA])
def test_d3_annullo_un_iscrizione_non_confermata(
    client: TestClient, db: Engine, stato: StatoIscrizione
) -> None:
    anna = persona(db, "Anna")
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione(db), stato)

    risposta = annulla(client, anna, iscrizione_id)

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "Annullata"
    [evento] = client.get(f"{URL}/{iscrizione_id}", headers=anna).json()["storia"]
    assert (evento["stato_da"], evento["stato_a"]) == (stato.value, "Annullata")


def test_r5_confermata_prima_della_scadenza_libera_il_posto(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    # Scadenza predefinita: 3 giorni. Ne mancano 4.
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=4))
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione_id, S.CONFERMATA)

    risposta = annulla(client, anna, iscrizione_id)

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "Annullata"
    assert posti_confermati(db, edizione_id) == 0


@pytest.mark.parametrize("giorni", [3, 1, 0])
def test_r5_confermata_dentro_la_scadenza_409(client: TestClient, db: Engine, giorni: int) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=giorni))
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione_id, S.CONFERMATA)

    risposta = annulla(client, anna, iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/scadenza-annullamento-superata"
    assert posti_confermati(db, edizione_id) == 1
    assert client.get(f"{URL}/{iscrizione_id}", headers=anna).json()["storia"] == []


def test_r5_la_scadenza_viene_dalla_configurazione(
    client: TestClient, db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACADEMY_SCADENZA_ANNULLAMENTO_GIORNI", "10")
    impostazioni.cache_clear()
    anna = persona(db, "Anna")
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=5))
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione_id, S.CONFERMATA)

    risposta = annulla(client, anna, iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/scadenza-annullamento-superata"


def test_non_annullo_l_iscrizione_di_un_altra_persona(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione(db), S.RICHIESTA)

    risposta = annulla(client, persona(db, "Bruno"), iscrizione_id)

    assert risposta.status_code == 403


# --- US-11 · Audit -----------------------------------------------------------------


@pytest.mark.parametrize("stato", [S.ANNULLATA, S.RIFIUTATA, S.COMPLETATA])
def test_r7_transizione_rifiutata_senza_audit(
    client: TestClient, db: Engine, stato: StatoIscrizione
) -> None:
    anna = persona(db, "Anna")
    iscrizione_id = iscrizione(db, int(anna["X-Persona-Id"]), edizione(db), stato)

    risposta = annulla(client, anna, iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/transizione-non-consentita"
    assert client.get(f"{URL}/{iscrizione_id}", headers=anna).json()["storia"] == []


@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "DELETE"])
def test_l_audit_non_si_modifica_tramite_l_api(client: TestClient, db: Engine, metodo: str) -> None:
    anna = persona(db, "Anna")
    creata = richiedi(client, anna, edizione(db)).json()

    risposta = client.request(metodo, f"{URL}/{creata['id']}", headers=anna)

    assert risposta.status_code == 405
    assert len(client.get(f"{URL}/{creata['id']}", headers=anna).json()["storia"]) == 1


def test_la_storia_registra_autore_istante_stati_e_motivo(client: TestClient, db: Engine) -> None:
    org = organigramma(db)
    edizione_id = edizione(db)
    creata = richiedi(client, org("Anna"), edizione_id).json()
    client.post(
        f"{URL}/{creata['id']}/rifiuto",
        json={"motivo": "Budget esaurito"},
        headers=org("Rossa"),
    )

    storia = client.get(f"{URL}/{creata['id']}", headers=org("Admin")).json()["storia"]

    assert [(e["stato_da"], e["stato_a"], e["autore_id"], e["motivo"]) for e in storia] == [
        (None, "Richiesta", org.ids["Anna"], None),
        ("Richiesta", "Rifiutata", org.ids["Rossa"], "Budget esaurito"),
    ]
    assert all(e["avvenuto_il"] for e in storia)
