from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from academy_hub.config import Impostazioni, impostazioni
from academy_hub.main import crea_app


@pytest.fixture(autouse=True)
def impostazioni_rilette() -> Iterator[None]:
    """Ogni test rilegge le variabili d'ambiente che ha impostato."""
    impostazioni.cache_clear()
    yield
    impostazioni.cache_clear()


def test_health_risponde_ok() -> None:
    risposta = TestClient(crea_app()).get("/health")

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "ok"


def test_ambiente_letto_dalla_variabile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", "collaudo")
    monkeypatch.setenv("ACADEMY_IDENTITA", "databricks")

    assert TestClient(crea_app()).get("/health").json()["ambiente"] == "collaudo"


def test_x_persona_id_ignorato_con_la_configurazione_predefinita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un deploy che non imposta nulla vuole un token OIDC, non l'identità provvisoria."""
    monkeypatch.delenv("ACADEMY_IDENTITA", raising=False)
    monkeypatch.delenv("ACADEMY_AMBIENTE", raising=False)

    risposta = TestClient(crea_app()).get("/api/v1/catalogo", headers={"X-Persona-Id": "1"})

    assert risposta.status_code == 401
    assert risposta.headers["Content-Type"] == "application/problem+json"
    assert risposta.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.parametrize("ambiente", ["collaudo", "produzione"])
def test_identita_provvisoria_vietata_fuori_dal_locale(
    monkeypatch: pytest.MonkeyPatch, ambiente: str
) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", ambiente)
    monkeypatch.setenv("ACADEMY_IDENTITA", "provvisoria")

    with pytest.raises(ValidationError, match="identita=provvisoria"):
        Impostazioni()


def test_identita_provvisoria_vietata_senza_ambiente_dichiarato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#58: `locale` è il default, ma un deploy che dimentica l'ambiente non deve
    accettare X-Persona-Id."""
    monkeypatch.delenv("ACADEMY_AMBIENTE", raising=False)
    monkeypatch.setenv("ACADEMY_IDENTITA", "provvisoria")

    with pytest.raises(ValidationError, match="ACADEMY_AMBIENTE=locale dichiarato"):
        Impostazioni()


def test_identita_provvisoria_ammessa_con_locale_dichiarato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", "locale")
    monkeypatch.setenv("ACADEMY_IDENTITA", "provvisoria")

    assert Impostazioni().identita == "provvisoria"


def test_identita_databricks_vietata_in_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza il proxy di Databricks Apps chiunque può scrivere X-Forwarded-Email."""
    monkeypatch.setenv("ACADEMY_AMBIENTE", "locale")
    monkeypatch.setenv("ACADEMY_IDENTITA", "databricks")

    with pytest.raises(ValidationError, match="identita=databricks"):
        Impostazioni()


@pytest.mark.parametrize("ambiente", ["collaudo", "produzione"])
def test_identita_databricks_ammessa_sulla_piattaforma(
    monkeypatch: pytest.MonkeyPatch, ambiente: str
) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", ambiente)
    monkeypatch.setenv("ACADEMY_IDENTITA", "databricks")

    assert Impostazioni().identita == "databricks"


@pytest.mark.parametrize(
    ("emittente", "jwks"),
    [
        ("http://kc.test/realms/academy", None),
        ("https://kc.test/realms/academy", "http://kc.test/certs"),
    ],
)
def test_oidc_in_chiaro_vietato_fuori_dal_locale(
    monkeypatch: pytest.MonkeyPatch, emittente: str, jwks: str | None
) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", "collaudo")
    monkeypatch.setenv("ACADEMY_IDENTITA", "oidc")
    monkeypatch.setenv("ACADEMY_OIDC_EMITTENTE", emittente)
    if jwks is None:
        monkeypatch.delenv("ACADEMY_OIDC_JWKS_URL", raising=False)
    else:
        monkeypatch.setenv("ACADEMY_OIDC_JWKS_URL", jwks)

    with pytest.raises(ValidationError, match="https"):
        Impostazioni()


def test_oidc_https_ammesso_fuori_dal_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", "produzione")
    monkeypatch.setenv("ACADEMY_IDENTITA", "oidc")
    monkeypatch.setenv("ACADEMY_OIDC_EMITTENTE", "https://kc.test/realms/academy")
    monkeypatch.delenv("ACADEMY_OIDC_JWKS_URL", raising=False)

    assert Impostazioni().jwks_url.startswith("https://")


def test_jwks_url_derivato_dall_emittente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_OIDC_EMITTENTE", "http://kc.test/realms/academy")
    monkeypatch.delenv("ACADEMY_OIDC_JWKS_URL", raising=False)

    assert Impostazioni().jwks_url == "http://kc.test/realms/academy/protocol/openid-connect/certs"


@pytest.mark.parametrize("valore", ["abc", "1.5", "", "0", "-3"])
def test_x_persona_id_non_valido_401(monkeypatch: pytest.MonkeyPatch, valore: str) -> None:
    monkeypatch.setenv("ACADEMY_IDENTITA", "provvisoria")
    monkeypatch.setenv("ACADEMY_AMBIENTE", "locale")

    risposta = TestClient(crea_app()).get("/api/v1/catalogo", headers={"X-Persona-Id": valore})

    assert risposta.status_code == 401
    assert risposta.json()["type"] == "/problemi/non-autenticato"
