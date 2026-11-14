"""US-06 · Approvare o rifiutare, US-07 · Richieste da approvare, US-08 · Confermare un posto,
attraverso l'API. Organigramma in `tests/api.py`."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Iscrizione, Persona, Team
from academy_hub.dominio.errori import AzioneNonConsentita
from academy_hub.dominio.organigramma import verifica_decisore
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.dominio.tempo import oggi
from academy_hub.repository import persone

from .api import Organigramma, edizione, iscrizione, organigramma

pytestmark = pytest.mark.integrazione

S = StatoIscrizione
URL = "/api/v1/iscrizioni"
DA_APPROVARE = "/api/v1/richieste-da-approvare"


@pytest.fixture
def org(db: Engine) -> Organigramma:
    return organigramma(db)


def richiesta(db: Engine, org: Organigramma, nome: str, edizione_id: int | None = None) -> int:
    return iscrizione(db, org.ids[nome], edizione_id or edizione(db), S.RICHIESTA)


def approva(client: TestClient, chi: dict[str, str], iscrizione_id: int) -> httpx.Response:
    return client.post(f"{URL}/{iscrizione_id}/approvazione", headers=chi)


def rifiuta(
    client: TestClient, chi: dict[str, str], iscrizione_id: int, motivo: object = "Budget"
) -> httpx.Response:
    return client.post(f"{URL}/{iscrizione_id}/rifiuto", json={"motivo": motivo}, headers=chi)


def tipo(risposta: httpx.Response) -> str:
    return risposta.json()["type"]


# --- US-06 · Approvare o rifiutare -------------------------------------------------


def test_il_responsabile_approva_con_audit(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Anna")

    risposta = approva(client, org("Rossa"), iscrizione_id)

    assert risposta.status_code == 200
    approvata = risposta.json()
    assert approvata["stato"] == "Approvata"
    assert approvata["approvata_il"] is not None
    # La risposta riporta già l'istante del cambio, lo stesso che si rilegge dopo.
    letta = client.get(f"{URL}/{iscrizione_id}", headers=org("Anna")).json()
    assert approvata["aggiornata_il"] == letta["aggiornata_il"] == approvata["approvata_il"]
    [evento] = client.get(f"{URL}/{iscrizione_id}", headers=org("Anna")).json()["storia"]
    assert (evento["stato_da"], evento["stato_a"], evento["autore_id"]) == (
        "Richiesta",
        "Approvata",
        org.ids["Rossa"],
    )


def test_il_responsabile_rifiuta_con_motivo(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Anna")

    risposta = rifiuta(client, org("Rossa"), iscrizione_id, "Corso non pertinente")

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "Rifiutata"
    [evento] = client.get(f"{URL}/{iscrizione_id}", headers=org("Anna")).json()["storia"]
    assert evento["motivo"] == "Corso non pertinente"


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_il_motivo_del_rifiuto_e_obbligatorio(
    client: TestClient, db: Engine, org: Organigramma, motivo: object
) -> None:
    iscrizione_id = richiesta(db, org, "Anna")

    risposta = rifiuta(client, org("Rossa"), iscrizione_id, motivo)

    assert risposta.status_code == 422
    assert risposta.json()["errori"][0]["campo"] == "motivo"


def test_il_rifiuto_senza_corpo_e_422(client: TestClient, db: Engine, org: Organigramma) -> None:
    risposta = client.post(f"{URL}/{richiesta(db, org, 'Anna')}/rifiuto", headers=org("Rossa"))

    assert risposta.status_code == 422


@pytest.mark.parametrize("decide", [approva, rifiuta])
def test_r2_il_responsabile_di_un_altro_team_403(
    client: TestClient,
    db: Engine,
    org: Organigramma,
    decide: Callable[[TestClient, dict[str, str], int], httpx.Response],
) -> None:
    iscrizione_id = richiesta(db, org, "Anna")

    risposta = decide(client, org("Verdi"), iscrizione_id)

    assert risposta.status_code == 403
    assert tipo(risposta) == "/problemi/non-responsabile-diretto"


def test_d7_la_richiesta_di_un_responsabile_la_decide_il_team_padre(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Rossa")

    assert approva(client, org("Verdi"), iscrizione_id).status_code == 403
    assert approva(client, org("Dirigente"), iscrizione_id).status_code == 200


def test_d7_al_vertice_decide_l_amministratore(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Dirigente")

    assert approva(client, org("Rossa"), iscrizione_id).status_code == 403
    assert approva(client, org("Admin"), iscrizione_id).status_code == 200


def test_d9_decide_il_responsabile_in_carica(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Anna")
    # Anna passa al team Web dopo aver chiesto l'iscrizione.
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Persona, org.ids["Anna"]).team_id = org.team["Web"]

    assert approva(client, org("Rossa"), iscrizione_id).status_code == 403
    assert approva(client, org("Verdi"), iscrizione_id).status_code == 200


def test_r2_nessuno_approva_le_proprie_richieste(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iscrizione_id = richiesta(db, org, "Rossa")

    risposta = approva(client, org("Rossa"), iscrizione_id)

    assert risposta.status_code == 403
    assert tipo(risposta) == "/problemi/auto-approvazione"


@pytest.mark.parametrize("stato", [s for s in S if s is not S.RICHIESTA])
def test_r7_si_approva_solo_una_richiesta(
    client: TestClient, db: Engine, org: Organigramma, stato: StatoIscrizione
) -> None:
    iscrizione_id = iscrizione(db, org.ids["Anna"], edizione(db), stato)

    risposta = approva(client, org("Rossa"), iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/transizione-non-consentita"
    assert client.get(f"{URL}/{iscrizione_id}", headers=org("Anna")).json()["storia"] == []


def test_a_edizione_iniziata_non_si_approva_ma_si_rifiuta(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    edizione_id = edizione(db, inizio=oggi())
    prima = richiesta(db, org, "Anna", edizione_id)
    seconda = richiesta(db, org, "Bruno", edizione_id)

    risposta = approva(client, org("Rossa"), prima)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-iniziata"
    assert rifiuta(client, org("Rossa"), seconda).status_code == 200


def test_a_edizione_cancellata_non_si_approva(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    edizione_id = edizione(db)
    iscrizione_id = richiesta(db, org, "Anna", edizione_id)
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Edizione, edizione_id).cancellata_il = datetime.now(UTC)

    risposta = approva(client, org("Rossa"), iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-cancellata"


def test_iscrizione_inesistente_404(client: TestClient, org: Organigramma) -> None:
    assert approva(client, org("Rossa"), 999).status_code == 404


# --- US-07 · Elenco delle richieste da approvare -----------------------------------


def da_approvare(client: TestClient, chi: dict[str, str]) -> list[int]:
    return [v["iscrizione_id"] for v in client.get(DA_APPROVARE, headers=chi).json()["elementi"]]


def test_vedo_le_richieste_del_mio_team_dalla_piu_vecchia(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    bruno = richiesta(db, org, "Bruno")
    anna = richiesta(db, org, "Anna")
    richiesta(db, org, "Carla")  # altro team
    richiesta(db, org, "Rossa")  # la mia: la decide il Dirigente
    iscrizione(db, org.ids["Anna"], edizione(db), S.APPROVATA)  # già decisa

    pagina = client.get(DA_APPROVARE, headers=org("Rossa")).json()

    assert [v["iscrizione_id"] for v in pagina["elementi"]] == [bruno, anna]
    assert pagina["totale"] == 2
    voce = pagina["elementi"][0]
    assert voce["persona"] == {"id": org.ids["Bruno"], "nome": "Bruno"}
    assert {"edizione_id", "corso", "data_inizio", "richiesta_il"} <= voce.keys()


def test_l_elenco_e_paginato(client: TestClient, db: Engine, org: Organigramma) -> None:
    for _ in range(3):
        richiesta(db, org, "Anna")

    pagina = client.get(DA_APPROVARE, params={"limite": 2}, headers=org("Rossa")).json()

    assert (pagina["totale"], len(pagina["elementi"])) == (3, 2)


def test_un_dipendente_ha_l_elenco_vuoto(client: TestClient, db: Engine, org: Organigramma) -> None:
    richiesta(db, org, "Bruno")

    assert da_approvare(client, org("Anna")) == []


def test_l_elenco_coincide_con_chi_puo_decidere(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    """La regola SQL dell'elenco e quella del dominio (`verifica_decisore`) non divergono."""
    richieste = [richiesta(db, org, nome) for nome in org.ids]
    # Carla passa a Stage, sotto Dati, guidato da Admin: decide Admin come responsabile
    # (amministratore e responsabile insieme), non Rossa.
    # Rossa guida anche Analisi, sotto Dati, e ci si sposta: le sue richieste saltano
    # entrambi i suoi team e arrivano al Dirigente.
    with Session(db) as sessione, sessione.begin():
        stage = Team(nome="Stage", team_padre_id=org.team["Dati"], responsabile_id=org.ids["Admin"])
        analisi = Team(
            nome="Analisi", team_padre_id=org.team["Dati"], responsabile_id=org.ids["Rossa"]
        )
        sessione.add_all([stage, analisi])
        sessione.flush()
        sessione.get_one(Persona, org.ids["Carla"]).team_id = stage.id
        sessione.get_one(Persona, org.ids["Rossa"]).team_id = analisi.id

    with Session(db) as sessione:
        for nome, persona_id in org.ids.items():
            attore = persone.attore(sessione, persona_id)
            assert attore is not None
            elenco = set(da_approvare(client, org(nome)))
            for iscrizione_id in richieste:
                richiedente = sessione.get_one(Iscrizione, iscrizione_id).persona_id
                catena = persone.catena_responsabili(sessione, richiedente)
                try:
                    verifica_decisore(attore, richiedente, catena)
                    puo = True
                except AzioneNonConsentita:
                    puo = False
                assert (iscrizione_id in elenco) == puo, (nome, iscrizione_id)


# --- US-08 · Confermare un posto ---------------------------------------------------


def conferma(client: TestClient, chi: dict[str, str], iscrizione_id: int) -> httpx.Response:
    return client.post(f"{URL}/{iscrizione_id}/conferma", headers=chi)


def test_l_amministratore_conferma_o_mette_in_lista_d_attesa(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    edizione_id = edizione(db, capienza=1)
    prima = iscrizione(db, org.ids["Anna"], edizione_id, S.APPROVATA)
    seconda = iscrizione(db, org.ids["Bruno"], edizione_id, S.APPROVATA)

    assert conferma(client, org("Admin"), prima).json()["stato"] == "Confermata"
    assert conferma(client, org("Admin"), seconda).json()["stato"] == "InAttesa"
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 1


def test_solo_l_amministratore_conferma(client: TestClient, db: Engine, org: Organigramma) -> None:
    iscrizione_id = iscrizione(db, org.ids["Anna"], edizione(db), S.APPROVATA)

    assert conferma(client, org("Rossa"), iscrizione_id).status_code == 403


def test_a_edizione_iniziata_non_si_conferma(
    client: TestClient, db: Engine, org: Organigramma
) -> None:
    iniziata = edizione(db, inizio=oggi() - timedelta(days=1))
    iscrizione_id = iscrizione(db, org.ids["Anna"], iniziata, S.APPROVATA)

    risposta = conferma(client, org("Admin"), iscrizione_id)

    assert risposta.status_code == 409
    assert tipo(risposta) == "/problemi/edizione-iniziata"
