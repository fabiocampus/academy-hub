"""Chi sono e come si accede (issue #59): servono al frontend per login e menu per ruolo."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.api import PREFISSO
from academy_hub.api.rotte.profilo import configurazione_client
from academy_hub.config import Impostazioni

from .api import R
from .dati import crea_persona, crea_team


@pytest.mark.integrazione
def test_io_restituisce_la_persona_e_i_suoi_ruoli(client: TestClient, db: Engine) -> None:
    with Session(db) as sessione:
        anna = crea_persona(sessione, "Anna", ruoli=(R.DOCENTE, R.DIPENDENTE))
        sessione.commit()
        anna_id, team_id = anna.id, anna.team_id

    risposta = client.get(f"{PREFISSO}/io", headers={"X-Persona-Id": str(anna_id)})

    assert risposta.status_code == 200
    assert risposta.json() == {
        "persona_id": anna_id,
        "nome": "Anna",
        "email": "anna@esempio.test",
        "team_id": team_id,
        "ruoli": ["dipendente", "docente"],
        "responsabile_di_team": False,
    }


@pytest.mark.integrazione
def test_io_dice_se_la_persona_e_responsabile_di_un_team(client: TestClient, db: Engine) -> None:
    """Il responsabile non è un ruolo: decide chi è responsabile_id di un team (R2)."""
    with Session(db) as sessione:
        dati = crea_team(sessione, "Dati")
        rossa = crea_persona(sessione, "Rossa", dati, (R.DIPENDENTE,))
        dati.responsabile_id = rossa.id
        sessione.commit()
        rossa_id = rossa.id

    risposta = client.get(f"{PREFISSO}/io", headers={"X-Persona-Id": str(rossa_id)})

    assert risposta.json()["responsabile_di_team"] is True


@pytest.mark.integrazione
def test_io_senza_identita_e_401(client: TestClient) -> None:
    assert client.get(f"{PREFISSO}/io").status_code == 401


@pytest.mark.integrazione
def test_configurazione_e_pubblica(client: TestClient) -> None:
    """Il frontend la legge prima del login: niente identità."""
    risposta = client.get(f"{PREFISSO}/configurazione")

    assert risposta.status_code == 200
    assert risposta.json() == {"identita": "provvisoria", "oidc": None}


def test_configurazione_oidc_indica_emittente_e_client() -> None:
    impostazioni = Impostazioni(
        identita="oidc",
        oidc_emittente="http://localhost:8080/realms/academy",
        oidc_client_web="academy-web",
    )

    assert configurazione_client(impostazioni).model_dump() == {
        "identita": "oidc",
        "oidc": {
            "emittente": "http://localhost:8080/realms/academy",
            "client_id": "academy-web",
        },
    }


def test_configurazione_databricks_senza_oidc() -> None:
    """Su Databricks Apps il login lo fa la piattaforma, prima che la pagina arrivi."""
    impostazioni = Impostazioni(ambiente="collaudo", identita="databricks")

    assert configurazione_client(impostazioni).model_dump() == {
        "identita": "databricks",
        "oidc": None,
    }
