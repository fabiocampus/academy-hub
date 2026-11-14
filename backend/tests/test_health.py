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
