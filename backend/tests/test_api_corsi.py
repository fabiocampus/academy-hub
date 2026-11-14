"""US-01 · Creare e modificare un corso, attraverso l'API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from academy_hub.dominio.ruoli import Ruolo

from .api import persona

pytestmark = pytest.mark.integrazione


def test_l_amministratore_crea_un_corso(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.post(
        "/api/v1/corsi",
        json={"titolo": "SQL per analisti", "descrizione": "Le basi", "durata_ore": 8},
        headers=admin,
    )

    assert risposta.status_code == 201
    corso = risposta.json()
    assert (corso["titolo"], corso["descrizione"], corso["durata_ore"]) == (
        "SQL per analisti",
        "Le basi",
        8,
    )
    assert risposta.headers["Location"] == f"/api/v1/corsi/{corso['id']}"
    letto = client.get(f"/api/v1/corsi/{corso['id']}", headers=admin)
    assert letto.status_code == 200
    assert letto.json() == corso


CORSO = {"titolo": "SQL per analisti", "durata_ore": 8}


@pytest.mark.parametrize(
    ("dati", "campo"),
    [
        ({"titolo": "SQL", "durata_ore": 0}, "durata_ore"),
        ({"titolo": "SQL", "durata_ore": -3}, "durata_ore"),
        ({"titolo": "   ", "durata_ore": 8}, "titolo"),
        ({"durata_ore": 8}, "titolo"),
    ],
)
def test_dati_non_validi_rifiutati_con_422_e_il_campo(
    client: TestClient, db: Engine, dati: dict[str, object], campo: str
) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.post("/api/v1/corsi", json=dati, headers=admin)

    assert risposta.status_code == 422
    assert risposta.headers["Content-Type"] == "application/problem+json"
    problema = risposta.json()
    assert problema["type"] == "/problemi/dati-non-validi"
    assert problema["status"] == 422
    assert [e["campo"] for e in problema["errori"]] == [campo]


@pytest.mark.parametrize("ruoli", [(Ruolo.DIPENDENTE,), (Ruolo.RESPONSABILE, Ruolo.DIPENDENTE)])
def test_dipendente_o_responsabile_non_crea_corsi(
    client: TestClient, db: Engine, ruoli: tuple[Ruolo, ...]
) -> None:
    risposta = client.post("/api/v1/corsi", json=CORSO, headers=persona(db, "Anna", *ruoli))

    assert risposta.status_code == 403
    assert risposta.json()["type"] == "/problemi/azione-non-consentita"


@pytest.mark.parametrize("header", [{}, {"X-Persona-Id": "999"}])
def test_senza_identita_valida_401(client: TestClient, header: dict[str, str]) -> None:
    risposta = client.post("/api/v1/corsi", json=CORSO, headers=header)

    assert risposta.status_code == 401
    assert risposta.json()["type"] == "/problemi/non-autenticato"


def test_corso_inesistente_404(client: TestClient, db: Engine) -> None:
    risposta = client.get("/api/v1/corsi/999", headers=persona(db, "Anna"))

    assert risposta.status_code == 404
    assert risposta.json()["type"] == "/problemi/non-trovato"


def crea(client: TestClient, admin: dict[str, str]) -> tuple[int, str]:
    risposta = client.post("/api/v1/corsi", json=CORSO, headers=admin)
    return risposta.json()["id"], risposta.headers["ETag"]


def test_modifica_con_l_etag_letto(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, versione = crea(client, admin)

    risposta = client.patch(
        f"/api/v1/corsi/{corso_id}",
        json={"titolo": "SQL avanzato", "durata_ore": 16},
        headers={**admin, "If-Match": versione},
    )

    assert risposta.status_code == 200
    assert (risposta.json()["titolo"], risposta.json()["durata_ore"]) == ("SQL avanzato", 16)
    assert risposta.headers["ETag"] != versione
    assert client.get(f"/api/v1/corsi/{corso_id}", headers=admin).json() == risposta.json()


def test_modifica_senza_if_match_428(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, _ = crea(client, admin)

    risposta = client.patch(f"/api/v1/corsi/{corso_id}", json={"titolo": "X"}, headers=admin)

    assert risposta.status_code == 428
    assert risposta.json()["type"] == "/problemi/precondizione-richiesta"


def test_modifica_con_etag_superato_412(client: TestClient, db: Engine) -> None:
    """Due amministratori leggono lo stesso corso: vince il primo che salva."""
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, letto = crea(client, admin)
    primo = client.patch(
        f"/api/v1/corsi/{corso_id}", json={"titolo": "Primo"}, headers={**admin, "If-Match": letto}
    )
    assert primo.status_code == 200

    secondo = client.patch(
        f"/api/v1/corsi/{corso_id}",
        json={"titolo": "Secondo"},
        headers={**admin, "If-Match": letto},
    )

    assert secondo.status_code == 412
    assert secondo.json()["type"] == "/problemi/versione-non-corrispondente"
    assert client.get(f"/api/v1/corsi/{corso_id}", headers=admin).json()["titolo"] == "Primo"


def test_modifica_vietata_al_dipendente(client: TestClient, db: Engine) -> None:
    corso_id, versione = crea(client, persona(db, "Admin", Ruolo.ADMIN_ACADEMY))

    risposta = client.patch(
        f"/api/v1/corsi/{corso_id}",
        json={"titolo": "X"},
        headers={**persona(db, "Anna"), "If-Match": versione},
    )

    assert risposta.status_code == 403


@pytest.mark.parametrize("if_match", ['W/"1"', "1", '"abc"'])
def test_if_match_malformato_412(client: TestClient, db: Engine, if_match: str) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, _ = crea(client, admin)

    risposta = client.patch(
        f"/api/v1/corsi/{corso_id}", json={"titolo": "X"}, headers={**admin, "If-Match": if_match}
    )

    assert risposta.status_code == 412
    assert risposta.json()["type"] == "/problemi/versione-non-corrispondente"


def test_if_match_asterisco_428(client: TestClient, db: Engine) -> None:
    """`*` vale per qualunque versione: aggirerebbe la concorrenza ottimistica (ADR-0005)."""
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, _ = crea(client, admin)

    risposta = client.patch(
        f"/api/v1/corsi/{corso_id}", json={"titolo": "X"}, headers={**admin, "If-Match": "*"}
    )

    assert risposta.status_code == 428
    assert risposta.json()["type"] == "/problemi/precondizione-richiesta"


def test_archiviazione_vietata_al_dipendente_403(client: TestClient, db: Engine) -> None:
    corso_id, versione = crea(client, persona(db, "Admin", Ruolo.ADMIN_ACADEMY))

    risposta = client.post(
        f"/api/v1/corsi/{corso_id}/archiviazione",
        headers={**persona(db, "Anna"), "If-Match": versione},
    )

    assert risposta.status_code == 403


def test_archiviazione_senza_if_match_428(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, _ = crea(client, admin)

    risposta = client.post(f"/api/v1/corsi/{corso_id}/archiviazione", headers=admin)

    assert risposta.status_code == 428


def test_archiviazione_di_un_corso_inesistente_404(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)

    risposta = client.post("/api/v1/corsi/999/archiviazione", headers={**admin, "If-Match": '"1"'})

    assert risposta.status_code == 404


@pytest.mark.parametrize("campo", ["titolo", "descrizione", "durata_ore"])
def test_null_nella_modifica_del_corso_422(client: TestClient, db: Engine, campo: str) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso_id, versione = crea(client, admin)

    risposta = client.patch(
        f"/api/v1/corsi/{corso_id}", json={campo: None}, headers={**admin, "If-Match": versione}
    )

    assert risposta.status_code == 422
    assert [e["campo"] for e in risposta.json()["errori"]] == [campo]
