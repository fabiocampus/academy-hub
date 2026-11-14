"""US-03 · Consultare il catalogo; US-01 · i corsi archiviati escono dal catalogo."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Corso, Edizione
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi

from .api import persona
from .dati import crea_iscrizione, crea_persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
# Lo stesso calendario del servizio (Europe/Rome), anche se la CI gira in UTC.
OGGI = oggi()


def pianifica(
    sessione: Session,
    titolo: str,
    tra_giorni: int,
    capienza: int = 10,
    posti_confermati: int = 0,
) -> Edizione:
    corso = Corso(titolo=titolo, durata_ore=8)
    sessione.add(corso)
    sessione.flush()
    inizio = OGGI + timedelta(days=tra_giorni)
    edizione = Edizione(
        corso_id=corso.id,
        data_inizio=inizio,
        data_fine=inizio + timedelta(days=1),
        capienza=capienza,
        posti_confermati=posti_confermati,
    )
    sessione.add(edizione)
    sessione.flush()
    return edizione


def catalogo(client: TestClient, header: dict[str, str], **parametri: str | int) -> dict[str, Any]:
    risposta = client.get("/api/v1/catalogo", params=parametri, headers=header)
    assert risposta.status_code == 200, risposta.text
    return risposta.json()


def test_solo_edizioni_non_iniziate_per_data_di_inizio(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        pianifica(sessione, "Tra dieci giorni", 10)
        pianifica(sessione, "Già iniziata", -1)
        pianifica(sessione, "Oggi", 0)
        pianifica(sessione, "Domani", 1)
        cancellata = pianifica(sessione, "Cancellata", 5)
        cancellata.cancellata_il = datetime.now(UTC)
    anna = persona(db, "Anna")

    pagina = catalogo(client, anna)

    assert [v["corso"]["titolo"] for v in pagina["elementi"]] == ["Domani", "Tra dieci giorni"]
    assert pagina["totale"] == 2


def test_ogni_voce_mostra_posti_e_lista_d_attesa(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        edizione = pianifica(sessione, "SQL", 10, capienza=3, posti_confermati=3)
        for nome in ("Bruno", "Carla"):
            crea_iscrizione(sessione, crea_persona(sessione, nome), edizione, S.IN_ATTESA)
        crea_iscrizione(sessione, crea_persona(sessione, "Dora"), edizione, S.APPROVATA)
        edizione_id, corso_id = edizione.id, edizione.corso_id

    [voce] = catalogo(client, persona(db, "Anna"))["elementi"]

    assert voce == {
        "edizione_id": edizione_id,
        "corso": {"id": corso_id, "titolo": "SQL", "durata_ore": 8},
        "data_inizio": (OGGI + timedelta(days=10)).isoformat(),
        "data_fine": (OGGI + timedelta(days=11)).isoformat(),
        "capienza": 3,
        "posti_confermati": 3,
        "lista_attesa": 2,
        "mia_iscrizione": None,
    }


def test_paginato(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        for giorni in range(1, 6):
            pianifica(sessione, f"Corso {giorni}", giorni)
    anna = persona(db, "Anna")

    pagina = catalogo(client, anna, limite=2, offset=2)

    assert [v["corso"]["titolo"] for v in pagina["elementi"]] == ["Corso 3", "Corso 4"]
    assert (pagina["totale"], pagina["limite"], pagina["offset"]) == (5, 2, 2)


@pytest.mark.parametrize("parametri", [{"limite": 0}, {"limite": 101}, {"offset": -1}])
def test_paginazione_fuori_dai_limiti_422(
    client: TestClient, db: Engine, parametri: dict[str, int]
) -> None:
    risposta = client.get("/api/v1/catalogo", params=parametri, headers=persona(db, "Anna"))

    assert risposta.status_code == 422
    assert [e["campo"] for e in risposta.json()["errori"]] == list(parametri)


def test_filtro_per_titolo_e_intervallo_di_date(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        pianifica(sessione, "SQL per analisti", 5)
        pianifica(sessione, "SQL avanzato", 20)
        pianifica(sessione, "Python", 6)
    anna = persona(db, "Anna")

    per_titolo = catalogo(client, anna, titolo="sql")
    per_date = catalogo(
        client,
        anna,
        dal=(OGGI + timedelta(days=5)).isoformat(),
        al=(OGGI + timedelta(days=6)).isoformat(),
    )

    assert [v["corso"]["titolo"] for v in per_titolo["elementi"]] == [
        "SQL per analisti",
        "SQL avanzato",
    ]
    assert [v["corso"]["titolo"] for v in per_date["elementi"]] == ["SQL per analisti", "Python"]


def test_mostra_lo_stato_della_mia_iscrizione_attiva(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        con_richiesta = pianifica(sessione, "Con richiesta", 5)
        con_annullata = pianifica(sessione, "Con annullata", 6)
        pianifica(sessione, "Senza", 7)
        anna = crea_persona(sessione, "Anna")
        altra = crea_persona(sessione, "Bruno")
        crea_iscrizione(sessione, anna, con_richiesta, S.RICHIESTA)
        crea_iscrizione(sessione, anna, con_annullata, S.ANNULLATA)
        crea_iscrizione(sessione, altra, con_annullata, S.APPROVATA)
        anna_id = anna.id

    voci = catalogo(client, {"X-Persona-Id": str(anna_id)})["elementi"]

    assert [(v["corso"]["titolo"], v["mia_iscrizione"]) for v in voci] == [
        ("Con richiesta", {"stato": "Richiesta"}),
        ("Con annullata", None),
        ("Senza", None),
    ]


def test_corso_archiviato_esce_dal_catalogo(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione, sessione.begin():
        archiviato = pianifica(sessione, "Archiviato", 5)
        pianifica(sessione, "Attivo", 6)
        corso_id, edizione_id = archiviato.corso_id, archiviato.id
        admin = crea_persona(sessione, "Admin", ruoli=(Ruolo.ADMIN_ACADEMY,))
        admin_header = {"X-Persona-Id": str(admin.id)}
    versione = client.get(f"/api/v1/corsi/{corso_id}", headers=admin_header).headers["ETag"]

    archiviazione = client.post(
        f"/api/v1/corsi/{corso_id}/archiviazione", headers={**admin_header, "If-Match": versione}
    )

    assert archiviazione.status_code == 200
    assert archiviazione.json()["archiviato_il"] is not None
    titoli = [v["corso"]["titolo"] for v in catalogo(client, admin_header)["elementi"]]
    assert titoli == ["Attivo"]
    # Le edizioni restano: servono ai report.
    with Session(db) as sessione:
        assert sessione.get(Edizione, edizione_id) is not None


def test_dalla_pianificazione_al_catalogo(client: TestClient, db: Engine) -> None:
    """End-to-end solo via HTTP: corso, edizione, poi il dipendente la trova nel catalogo."""
    admin = persona(db, "Admin", Ruolo.ADMIN_ACADEMY)
    corso = client.post(
        "/api/v1/corsi", json={"titolo": "Python per analisti", "durata_ore": 12}, headers=admin
    ).json()
    inizio = OGGI + timedelta(days=10)
    edizione = client.post(
        "/api/v1/edizioni",
        json={
            "corso_id": corso["id"],
            "data_inizio": inizio.isoformat(),
            "data_fine": (inizio + timedelta(days=2)).isoformat(),
            "capienza": 15,
        },
        headers=admin,
    ).json()

    pagina = catalogo(client, persona(db, "Anna"))

    assert pagina["totale"] == 1
    assert pagina["elementi"] == [
        {
            "edizione_id": edizione["id"],
            "corso": {"id": corso["id"], "titolo": "Python per analisti", "durata_ore": 12},
            "data_inizio": inizio.isoformat(),
            "data_fine": (inizio + timedelta(days=2)).isoformat(),
            "capienza": 15,
            "posti_confermati": 0,
            "lista_attesa": 0,
            "mia_iscrizione": None,
        }
    ]
