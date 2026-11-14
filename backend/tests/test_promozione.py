"""US-09 · Promozione dalla lista d'attesa, e aumento di capienza (US-02), attraverso l'API."""

from datetime import UTC, datetime, timedelta

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Iscrizione
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi

from .api import edizione, iscrizione, persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
URL = "/api/v1/iscrizioni"
# Istanti di approvazione dei test: contano solo l'ordine (R4).
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def id_di(chi: dict[str, str]) -> int:
    return int(chi["X-Persona-Id"])


def stato(db: Engine, iscrizione_id: int) -> StatoIscrizione:
    with Session(db) as sessione:
        return sessione.get_one(Iscrizione, iscrizione_id).stato


def posti(db: Engine, edizione_id: int) -> int:
    with Session(db) as sessione:
        return sessione.get_one(Edizione, edizione_id).posti_confermati


def lista_d_attesa(db: Engine, edizione_id: int, quanti: int) -> list[int]:
    """`quanti` iscrizioni InAttesa di persone nuove, approvate a un minuto l'una dall'altra."""
    return [
        iscrizione(
            db,
            id_di(persona(db, f"Attesa{n}")),
            edizione_id,
            S.IN_ATTESA,
            approvata_il=T0 + timedelta(minutes=n),
        )
        for n in range(quanti)
    ]


def annulla(client: TestClient, chi: dict[str, str], iscrizione_id: int) -> httpx.Response:
    return client.post(f"{URL}/{iscrizione_id}/annullamento", headers=chi)


def test_r4_annullando_una_confermata_passa_il_primo_in_lista(
    client: TestClient, db: Engine
) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db, capienza=1)
    confermata = iscrizione(db, id_di(anna), edizione_id, S.CONFERMATA)
    primo, secondo = lista_d_attesa(db, edizione_id, 2)

    risposta = annulla(client, anna, confermata)

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "Annullata"
    assert (stato(db, primo), stato(db, secondo)) == (S.CONFERMATA, S.IN_ATTESA)
    assert posti(db, edizione_id) == 1


def test_la_promozione_ha_audit_con_autore_sistema(client: TestClient, db: Engine) -> None:
    anna = persona(db, "Anna")
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db, capienza=1)
    confermata = iscrizione(db, id_di(anna), edizione_id, S.CONFERMATA)
    [promossa] = lista_d_attesa(db, edizione_id, 1)

    annulla(client, anna, confermata)

    [evento] = client.get(f"{URL}/{promossa}", headers=admin).json()["storia"]
    assert (evento["stato_da"], evento["stato_a"], evento["autore_id"]) == (
        "InAttesa",
        "Confermata",
        None,
    )


def test_r4_passa_chi_e_stato_approvato_prima_anche_se_ha_chiesto_dopo(
    client: TestClient, db: Engine
) -> None:
    anna = persona(db, "Anna")
    edizione_id = edizione(db, capienza=1)
    confermata = iscrizione(db, id_di(anna), edizione_id, S.CONFERMATA)
    # Richiesta prima (id e istante di richiesta minori), approvata dopo.
    chiesto_prima = iscrizione(
        db, id_di(persona(db, "Bruno")), edizione_id, S.IN_ATTESA, T0 + timedelta(hours=1)
    )
    approvato_prima = iscrizione(db, id_di(persona(db, "Carla")), edizione_id, S.IN_ATTESA, T0)

    annulla(client, anna, confermata)

    assert stato(db, approvato_prima) is S.CONFERMATA
    assert stato(db, chiesto_prima) is S.IN_ATTESA


def test_annullare_un_in_attesa_non_promuove_nessuno(client: TestClient, db: Engine) -> None:
    edizione_id = edizione(db, capienza=1)
    iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.CONFERMATA)
    bruno = persona(db, "Bruno")
    in_attesa = iscrizione(db, id_di(bruno), edizione_id, S.IN_ATTESA, T0)
    [dopo] = lista_d_attesa(db, edizione_id, 1)

    assert annulla(client, bruno, in_attesa).status_code == 200

    assert stato(db, dopo) is S.IN_ATTESA
    assert posti(db, edizione_id) == 1


def test_r4_la_conferma_non_scavalca_la_lista_d_attesa(client: TestClient, db: Engine) -> None:
    """Un posto libero con la lista non vuota va al primo in lista, non a chi si conferma ora.

    Con la promozione nella stessa transazione non dovrebbe succedere; la conferma ripara
    comunque lo stato, come il job (ADR-0007).
    """
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db, capienza=1)
    [in_lista] = lista_d_attesa(db, edizione_id, 1)
    approvata = iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.APPROVATA)

    risposta = client.post(f"{URL}/{approvata}/conferma", headers=admin)

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "InAttesa"
    assert stato(db, in_lista) is S.CONFERMATA
    assert posti(db, edizione_id) == 1


# --- US-02 · Aumento di capienza ---------------------------------------------------


def modifica_capienza(
    client: TestClient, admin: dict[str, str], edizione_id: int, capienza: int
) -> httpx.Response:
    letta = client.get(f"/api/v1/edizioni/{edizione_id}", headers=admin)
    return client.patch(
        f"/api/v1/edizioni/{edizione_id}",
        json={"capienza": capienza},
        headers={**admin, "If-Match": letta.headers["ETag"]},
    )


def test_us02_aumentare_la_capienza_promuove_i_primi_in_lista(
    client: TestClient, db: Engine
) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db, capienza=1)
    iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.CONFERMATA)
    primo, secondo, terzo = lista_d_attesa(db, edizione_id, 3)

    risposta = modifica_capienza(client, admin, edizione_id, 3)

    assert risposta.status_code == 200
    assert (risposta.json()["capienza"], risposta.json()["posti_confermati"]) == (3, 3)
    assert [stato(db, i) for i in (primo, secondo, terzo)] == [
        S.CONFERMATA,
        S.CONFERMATA,
        S.IN_ATTESA,
    ]
    # L'ETag della risposta è quello della risorsa dopo le promozioni.
    letta = client.get(f"/api/v1/edizioni/{edizione_id}", headers=admin)
    assert letta.headers["ETag"] == risposta.headers["ETag"]


def test_d2_a_edizione_iniziata_nessuno_viene_promosso(client: TestClient, db: Engine) -> None:
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    edizione_id = edizione(db, capienza=1, inizio=oggi() - timedelta(days=1))
    iscrizione(db, id_di(persona(db, "Anna")), edizione_id, S.CONFERMATA)
    [in_lista] = lista_d_attesa(db, edizione_id, 1)

    risposta = modifica_capienza(client, admin, edizione_id, 2)

    assert risposta.status_code == 200
    assert stato(db, in_lista) is S.IN_ATTESA
    assert posti(db, edizione_id) == 1
