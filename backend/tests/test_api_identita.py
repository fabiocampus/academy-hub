"""US-16: identità da token OIDC, ruoli dal database (ADR-0008)."""

import re
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.api import PREFISSO
from academy_hub.api.identita import Databricks, Oidc
from academy_hub.main import crea_app

from .api import R
from .dati import crea_persona
from .oidc import EMITTENTE, PUBBLICO, ProviderFinto

pytestmark = pytest.mark.integrazione


@pytest.fixture(scope="module")
def provider() -> ProviderFinto:
    return ProviderFinto()


@pytest.fixture
def client(db: Engine, provider: ProviderFinto) -> Iterator[TestClient]:
    """App configurata come in docker compose: identità dal token, non da X-Persona-Id."""
    with TestClient(crea_app(motore=db, identita=provider.oidc())) as client:
        yield client


def _persona(db: Engine, nome: str, *ruoli: R) -> int:
    with Session(db) as sessione:
        p = crea_persona(sessione, nome, ruoli=ruoli or (R.DIPENDENTE,))
        sessione.commit()
        return p.id


def test_token_valido_di_una_persona_registrata(
    client: TestClient, db: Engine, provider: ProviderFinto
) -> None:
    _persona(db, "Anna")

    risposta = client.get(
        f"{PREFISSO}/catalogo", headers=provider.intestazioni("anna@esempio.test")
    )

    assert risposta.status_code == 200


def test_attore_e_la_persona_dell_email(
    client: TestClient, db: Engine, provider: ProviderFinto
) -> None:
    """Le iscrizioni elencate sono quelle della persona del token, non di altri."""
    anna = _persona(db, "Anna")
    _persona(db, "Bruno")

    risposta = client.get(
        f"{PREFISSO}/iscrizioni", headers=provider.intestazioni("ANNA@esempio.test")
    )

    assert risposta.status_code == 200
    assert all(i["persona_id"] == anna for i in risposta.json()["elementi"])


def test_token_valido_ma_persona_non_registrata_403(
    client: TestClient, provider: ProviderFinto
) -> None:
    risposta = client.get(
        f"{PREFISSO}/catalogo", headers=provider.intestazioni("sconosciuta@esempio.test")
    )

    assert risposta.status_code == 403
    assert risposta.json()["type"] == "/problemi/persona-non-registrata"


def test_senza_token_401_con_www_authenticate(client: TestClient) -> None:
    risposta = client.get(f"{PREFISSO}/catalogo")

    assert risposta.status_code == 401
    assert risposta.headers["Content-Type"] == "application/problem+json"
    assert risposta.headers["WWW-Authenticate"] == 'Bearer realm="academy-hub"'


def test_x_persona_id_ignorato_con_oidc(client: TestClient, db: Engine) -> None:
    anna = _persona(db, "Anna", R.DIPENDENTE, R.ADMIN_ACADEMY)

    risposta = client.get(f"{PREFISSO}/catalogo", headers={"X-Persona-Id": str(anna)})

    assert risposta.status_code == 401


def test_token_scaduto_401(client: TestClient, db: Engine, provider: ProviderFinto) -> None:
    _persona(db, "Anna")

    risposta = client.get(
        f"{PREFISSO}/catalogo", headers=provider.intestazioni("anna@esempio.test", exp=1)
    )

    assert risposta.status_code == 401
    assert risposta.json()["type"] == "/problemi/non-autenticato"


def test_ruoli_nel_token_ignorati(client: TestClient, db: Engine, provider: ProviderFinto) -> None:
    """I ruoli li decide l'applicazione: un ruolo dichiarato dal token non conta."""
    _persona(db, "Anna")
    intestazioni = provider.intestazioni(
        "anna@esempio.test",
        realm_access={"roles": ["admin_academy"]},
        ruoli=["admin_academy"],
    )

    risposta = client.post(
        f"{PREFISSO}/corsi",
        json={"titolo": "Python", "descrizione": "", "durata_ore": 8},
        headers=intestazioni,
    )

    assert risposta.status_code == 403
    assert risposta.json()["type"] == "/problemi/azione-non-consentita"


def test_ruolo_dal_database(client: TestClient, db: Engine, provider: ProviderFinto) -> None:
    _persona(db, "Alba", R.DIPENDENTE, R.ADMIN_ACADEMY)

    risposta = client.post(
        f"{PREFISSO}/corsi",
        json={"titolo": "Python", "descrizione": "", "durata_ore": 8},
        headers=provider.intestazioni("alba@esempio.test"),
    )

    assert risposta.status_code == 201


def test_provider_irraggiungibile_503(db: Engine, provider: ProviderFinto) -> None:
    def giu(_token: str) -> Any:
        raise jwt.PyJWKClientConnectionError("connessione rifiutata")

    with TestClient(crea_app(motore=db, identita=Oidc(EMITTENTE, PUBBLICO, giu))) as client:
        risposta = client.get(f"{PREFISSO}/catalogo", headers=provider.intestazioni())

    assert risposta.status_code == 503
    assert risposta.json()["type"] == "/problemi/identita-non-disponibile"


@pytest.fixture
def client_databricks(db: Engine) -> Iterator[TestClient]:
    """App come su Databricks Apps: identità dall'header del proxy."""
    with TestClient(crea_app(motore=db, identita=Databricks())) as client:
        yield client


def test_databricks_persona_dell_header(client_databricks: TestClient, db: Engine) -> None:
    _persona(db, "Anna")

    risposta = client_databricks.get(
        f"{PREFISSO}/catalogo", headers={"X-Forwarded-Email": "Anna@esempio.test"}
    )

    assert risposta.status_code == 200


@pytest.mark.parametrize(
    "intestazioni",
    [
        pytest.param({}, id="senza-header"),
        pytest.param({"Authorization": "Bearer qualcosa"}, id="solo-bearer"),
        pytest.param({"X-Persona-Id": "1"}, id="solo-x-persona-id"),
    ],
)
def test_databricks_senza_x_forwarded_email_401(
    client_databricks: TestClient, db: Engine, intestazioni: dict[str, str]
) -> None:
    _persona(db, "Anna")

    assert client_databricks.get(f"{PREFISSO}/catalogo", headers=intestazioni).status_code == 401


def test_databricks_persona_non_registrata_403(client_databricks: TestClient) -> None:
    risposta = client_databricks.get(
        f"{PREFISSO}/catalogo", headers={"X-Forwarded-Email": "nessuno@esempio.test"}
    )

    assert risposta.status_code == 403
    assert risposta.json()["type"] == "/problemi/persona-non-registrata"


def test_health_senza_identita(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def _rotte_api() -> list[tuple[str, str]]:
    """Ogni operazione del contratto sotto il prefisso dell'API (cioè tutte tranne /health)."""
    schema = crea_app(identita=ProviderFinto().oidc()).openapi()
    rotte = [
        (metodo.upper(), percorso)
        for percorso, operazioni in schema["paths"].items()
        if percorso.startswith(PREFISSO)
        for metodo in operazioni
    ]
    assert rotte
    return sorted(rotte)


@pytest.mark.parametrize(("metodo", "percorso"), _rotte_api())
def test_ogni_rotta_senza_identita_401(client: TestClient, metodo: str, percorso: str) -> None:
    """US-16: senza identità valida ogni rotta, tranne /health, risponde 401."""
    concreto = re.sub(r"\{[^}]+\}", "1", percorso)

    risposta = client.request(metodo, concreto, headers={"If-Match": '"1"'})

    assert risposta.status_code == 401, risposta.text
