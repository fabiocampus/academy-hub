import pytest
from fastapi.testclient import TestClient

from academy_hub.config import impostazioni
from academy_hub.main import crea_app


def test_health_risponde_ok() -> None:
    risposta = TestClient(crea_app()).get("/health")

    assert risposta.status_code == 200
    assert risposta.json()["stato"] == "ok"


def test_ambiente_letto_dalla_variabile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_AMBIENTE", "collaudo")
    impostazioni.cache_clear()
    try:
        assert TestClient(crea_app()).get("/health").json()["ambiente"] == "collaudo"
    finally:
        impostazioni.cache_clear()


def test_x_persona_id_ignorato_fuori_dall_ambiente_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'identità provvisoria della fase 5 non vale in collaudo né in produzione."""
    monkeypatch.setenv("ACADEMY_AMBIENTE", "collaudo")
    impostazioni.cache_clear()
    try:
        risposta = TestClient(crea_app()).get("/api/v1/catalogo", headers={"X-Persona-Id": "1"})
    finally:
        impostazioni.cache_clear()

    assert risposta.status_code == 401
    assert risposta.headers["Content-Type"] == "application/problem+json"
