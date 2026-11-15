"""Gestori degli errori che non nascono dal dominio: ultima difesa e imprevisti."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm.exc import StaleDataError

from academy_hub.main import crea_app


def app_che_solleva(errore: Exception) -> FastAPI:
    app = crea_app()

    @app.get("/esplodi")
    def esplodi() -> None:  # pyright: ignore[reportUnusedFunction]
        raise errore

    return app


def test_versione_superata_all_update_412() -> None:
    """`version_id_col` scopre la riga già cambiata: stesso problema di un ETag superato."""
    risposta = TestClient(app_che_solleva(StaleDataError("riga cambiata"))).get("/esplodi")

    assert risposta.status_code == 412
    assert risposta.headers["Content-Type"] == "application/problem+json"
    assert risposta.json()["type"] == "/problemi/versione-non-corrispondente"
    assert "riga cambiata" not in risposta.text


def test_errore_imprevisto_500_senza_dettagli_interni(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(
        app_che_solleva(RuntimeError("password=segreta nel messaggio")),
        raise_server_exceptions=False,
    )

    with caplog.at_level(logging.ERROR):
        risposta = client.get("/esplodi")

    assert risposta.status_code == 500
    assert risposta.headers["Content-Type"] == "application/problem+json"
    assert risposta.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "instance": "/esplodi",
    }
    assert "segreta" not in risposta.text
    assert "Errore imprevisto" in caplog.text
