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

    assert TestClient(crea_app()).get("/health").json()["ambiente"] == "collaudo"


def test_x_persona_id_ignorato_senza_identita_provvisoria(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un deploy che non imposta nulla non accetta l'identità provvisoria della fase 5."""
    monkeypatch.delenv("ACADEMY_IDENTITA_PROVVISORIA", raising=False)
    monkeypatch.delenv("ACADEMY_AMBIENTE", raising=False)

    risposta = TestClient(crea_app()).get("/api/v1/catalogo", headers={"X-Persona-Id": "1"})

    assert risposta.status_code == 401
    assert risposta.headers["Content-Type"] == "application/problem+json"


@pytest.mark.parametrize("ambiente", ["collaudo", "produzione"])
def test_identita_provvisoria_vietata_fuori_dal_locale(
    monkeypatch: pytest.MonkeyPatch, ambiente: str
) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", ambiente)
    monkeypatch.setenv("ACADEMY_IDENTITA_PROVVISORIA", "true")

    with pytest.raises(ValidationError, match="identita_provvisoria"):
        Impostazioni()


@pytest.mark.parametrize("valore", ["abc", "1.5", ""])
def test_x_persona_id_non_numerico_401(monkeypatch: pytest.MonkeyPatch, valore: str) -> None:
    monkeypatch.setenv("ACADEMY_IDENTITA_PROVVISORIA", "true")

    risposta = TestClient(crea_app()).get("/api/v1/catalogo", headers={"X-Persona-Id": valore})

    assert risposta.status_code == 401
    assert risposta.json()["type"] == "/problemi/non-autenticato"
