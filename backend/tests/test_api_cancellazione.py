"""US-18 · Cancellare un'edizione, attraverso l'API (D10)."""

from datetime import timedelta

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Iscrizione
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi
from academy_hub.repository.iscrizioni import eventi_audit

from .api import edizione, iscrizione, persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione


def cancella(client: TestClient, chi: dict[str, str], edizione_id: int) -> httpx.Response:
    return client.post(f"/api/v1/edizioni/{edizione_id}/cancellazione", headers=chi)


def id_di(chi: dict[str, str]) -> int:
    return int(chi["X-Persona-Id"])


def tipo(risposta: httpx.Response) -> str:
    assert risposta.headers["content-type"] == "application/problem+json"
    return risposta.json()["type"]


def una_per_stato(db: Engine, edizione_id: int) -> dict[StatoIscrizione, int]:
    """Un'iscrizione per ogni stato attivo, più una Rifiutata, di persone diverse."""
    stati = [S.RICHIESTA, S.APPROVATA, S.IN_ATTESA, S.CONFERMATA, S.RIFIUTATA]
    return {
        s: iscrizione(db, id_di(persona(db, f"Persona{s.value}")), edizione_id, s) for s in stati
    }


def test_d10_ogni_iscrizione_attiva_diventa_annullata(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    # Dentro la scadenza di R5 (3 giorni): la cancellazione la ignora.
    edizione_id = edizione(db, capienza=2, inizio=oggi() + timedelta(days=2))
    iscrizioni = una_per_stato(db, edizione_id)

    risposta = cancella(client, admin, edizione_id)

    assert risposta.status_code == 200
    assert risposta.json()["cancellata_il"] is not None
    assert risposta.json()["posti_confermati"] == 0
    with Session(db) as sessione:
        for stato_iniziale, iscrizione_id in iscrizioni.items():
            trovata = sessione.get_one(Iscrizione, iscrizione_id)
            eventi = eventi_audit(sessione, iscrizione_id)
            if stato_iniziale is S.RIFIUTATA:
                assert (trovata.stato, eventi) == (S.RIFIUTATA, [])
                continue
            assert trovata.stato is S.ANNULLATA
            [evento] = eventi
            assert (evento.stato_da, evento.stato_a, evento.motivo, evento.autore_id) == (
                stato_iniziale,
                S.ANNULLATA,
                "edizione-cancellata",
                id_di(admin),
            )


def test_l_edizione_resta_e_sparisce_dal_catalogo(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    anna = persona(db, "Anna")
    edizione_id = edizione(db)
    prima = client.get("/api/v1/edizioni/" + str(edizione_id), headers=admin)

    cancella(client, admin, edizione_id)

    letta = client.get(f"/api/v1/edizioni/{edizione_id}", headers=anna)
    assert letta.status_code == 200
    assert letta.json()["cancellata_il"] is not None
    assert letta.headers["ETag"] != prima.headers["ETag"]
    catalogo = client.get("/api/v1/catalogo", headers=anna).json()
    assert [v["edizione_id"] for v in catalogo["elementi"]] == []


@pytest.mark.parametrize("giorni", [0, -1])
def test_edizione_gia_iniziata_409(client: TestClient, db: Engine, giorni: int) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db, inizio=oggi() + timedelta(days=giorni))
    richiesta = iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.RICHIESTA)

    risposta = cancella(client, admin, edizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-iniziata"
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).cancellata_il is None
        assert sessione.get_one(Iscrizione, richiesta).stato is S.RICHIESTA


def test_cancellare_due_volte_non_cambia_nulla(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db)
    richiesta = iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.RICHIESTA)
    prima = cancella(client, admin, edizione_id)

    seconda = cancella(client, admin, edizione_id)

    assert seconda.status_code == 200
    assert seconda.json() == prima.json()
    assert seconda.headers["ETag"] == prima.headers["ETag"]
    with Session(db) as sessione:
        assert len(eventi_audit(sessione, richiesta)) == 1


def test_dopo_la_cancellazione_non_ci_si_iscrive(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db)
    cancella(client, admin, edizione_id)

    risposta = client.post(
        "/api/v1/iscrizioni", json={"edizione_id": edizione_id}, headers=persona(db, "Anna")
    )

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-cancellata"


def test_serve_l_amministratore_403(client: TestClient, db: Engine) -> None:
    edizione_id = edizione(db)

    risposta = cancella(
        client, persona(db, "Anna", Ruolo.DIPENDENTE, Ruolo.RESPONSABILE), edizione_id
    )

    assert risposta.status_code == 403
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).cancellata_il is None


def test_edizione_inesistente_404(client: TestClient, db: Engine) -> None:
    assert cancella(client, persona(db, "Admin", Ruolo.ADMIN_ACADEMY), 999).status_code == 404


def test_senza_identita_401(client: TestClient) -> None:
    assert client.post("/api/v1/edizioni/1/cancellazione").status_code == 401
