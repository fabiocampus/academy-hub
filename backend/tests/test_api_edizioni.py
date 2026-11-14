"""US-02 · Pianificare un'edizione, attraverso l'API."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione
from academy_hub.dominio.ruoli import Ruolo

from .api import persona

pytestmark = pytest.mark.integrazione

INIZIO = date.today() + timedelta(days=30)


def corso(client: TestClient, admin: dict[str, str]) -> int:
    risposta = client.post(
        "/api/v1/corsi", json={"titolo": "SQL per analisti", "durata_ore": 8}, headers=admin
    )
    return risposta.json()["id"]


def edizione(corso_id: int, **altro: object) -> dict[str, object]:
    return {
        "corso_id": corso_id,
        "data_inizio": INIZIO.isoformat(),
        "data_fine": (INIZIO + timedelta(days=1)).isoformat(),
        "capienza": 12,
        **altro,
    }


def test_l_amministratore_pianifica_un_edizione(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id = corso(client, admin)

    risposta = client.post("/api/v1/edizioni", json=edizione(corso_id), headers=admin)

    assert risposta.status_code == 201
    creata = risposta.json()
    assert creata["corso_id"] == corso_id
    assert (creata["data_inizio"], creata["capienza"], creata["posti_confermati"]) == (
        INIZIO.isoformat(),
        12,
        0,
    )
    assert creata["cancellata_il"] is None
    assert risposta.headers["Location"] == f"/api/v1/edizioni/{creata['id']}"
    letta = client.get(f"/api/v1/edizioni/{creata['id']}", headers=persona(db, "Anna"))
    assert letta.json() == creata
    assert letta.headers["ETag"] == risposta.headers["ETag"]


@pytest.mark.parametrize(
    ("altro", "campo"),
    [
        ({"data_fine": (INIZIO - timedelta(days=1)).isoformat()}, "data_fine"),
        ({"capienza": 0}, "capienza"),
        ({"capienza": -1}, "capienza"),
    ],
)
def test_date_o_capienza_non_validi_422(
    client: TestClient, db: Engine, altro: dict[str, object], campo: str
) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.post(
        "/api/v1/edizioni", json=edizione(corso(client, admin), **altro), headers=admin
    )

    assert risposta.status_code == 422
    assert [e["campo"] for e in risposta.json()["errori"]] == [campo]


def test_corso_inesistente_422(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.post("/api/v1/edizioni", json=edizione(999), headers=admin)

    assert risposta.status_code == 422
    assert [e["campo"] for e in risposta.json()["errori"]] == ["corso_id"]


def test_corso_archiviato_non_riceve_edizioni_409(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id = corso(client, admin)
    versione = client.get(f"/api/v1/corsi/{corso_id}", headers=admin).headers["ETag"]
    client.post(f"/api/v1/corsi/{corso_id}/archiviazione", headers={**admin, "If-Match": versione})

    risposta = client.post("/api/v1/edizioni", json=edizione(corso_id), headers=admin)

    assert risposta.status_code == 409
    assert risposta.json()["type"] == "/problemi/corso-archiviato"


def test_docente_deve_avere_il_ruolo(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    anna = int(persona(db, "Anna")["X-Persona-Id"])
    dario = int(persona(db, "Dario", Ruolo.DOCENTE)["X-Persona-Id"])
    corso_id = corso(client, admin)

    rifiutata = client.post(
        "/api/v1/edizioni", json=edizione(corso_id, docente_id=anna), headers=admin
    )
    accettata = client.post(
        "/api/v1/edizioni", json=edizione(corso_id, docente_id=dario), headers=admin
    )

    assert rifiutata.status_code == 422
    assert [e["campo"] for e in rifiutata.json()["errori"]] == ["docente_id"]
    assert accettata.status_code == 201
    assert accettata.json()["docente_id"] == dario


def test_il_dipendente_non_pianifica_403(client: TestClient, db: Engine) -> None:
    corso_id = corso(client, persona(db, "Admin", Ruolo.ADMIN_ACADEMY))

    risposta = client.post("/api/v1/edizioni", json=edizione(corso_id), headers=persona(db, "Anna"))

    assert risposta.status_code == 403


def pianifica(client: TestClient, db: Engine, posti_confermati: int) -> tuple[dict[str, str], int]:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = client.post(
        "/api/v1/edizioni", json=edizione(corso(client, admin), capienza=5), headers=admin
    ).json()["id"]
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Edizione, edizione_id).posti_confermati = posti_confermati
    return admin, edizione_id


def modifica(client: TestClient, admin: dict[str, str], edizione_id: int, **campi: object):
    versione = client.get(f"/api/v1/edizioni/{edizione_id}", headers=admin).headers["ETag"]
    return client.patch(
        f"/api/v1/edizioni/{edizione_id}", json=campi, headers={**admin, "If-Match": versione}
    )


def test_r3_capienza_sotto_i_confermati_409(client: TestClient, db: Engine) -> None:
    admin, edizione_id = pianifica(client, db, posti_confermati=4)

    risposta = modifica(client, admin, edizione_id, capienza=3)

    assert risposta.status_code == 409
    assert risposta.json()["type"] == "/problemi/capienza-sotto-confermati"
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).capienza == 5


def test_capienza_ridotta_fino_ai_confermati(client: TestClient, db: Engine) -> None:
    admin, edizione_id = pianifica(client, db, posti_confermati=4)

    risposta = modifica(client, admin, edizione_id, capienza=4)

    assert risposta.status_code == 200
    assert risposta.json()["capienza"] == 4


def test_date_modificate_incoerenti_con_quelle_salvate_422(client: TestClient, db: Engine) -> None:
    admin, edizione_id = pianifica(client, db, posti_confermati=0)

    risposta = modifica(
        client, admin, edizione_id, data_inizio=(INIZIO + timedelta(days=5)).isoformat()
    )

    assert risposta.status_code == 422
    assert [e["campo"] for e in risposta.json()["errori"]] == ["data_fine"]


def test_modifica_edizione_con_etag_superato_412(client: TestClient, db: Engine) -> None:
    admin, edizione_id = pianifica(client, db, posti_confermati=0)
    letto = client.get(f"/api/v1/edizioni/{edizione_id}", headers=admin).headers["ETag"]
    modifica(client, admin, edizione_id, capienza=8)

    risposta = client.patch(
        f"/api/v1/edizioni/{edizione_id}",
        json={"capienza": 9},
        headers={**admin, "If-Match": letto},
    )

    assert risposta.status_code == 412
