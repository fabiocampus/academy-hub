"""Log JSON e id di correlazione (fase 12, issue #108)."""

import io
import json
import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from academy_hub.main import crea_app
from academy_hub.osservabilita import FormatoJson, id_richiesta, nuovo_id

# Composta a runtime: lo stack riporta le righe del sorgente, non i valori.
EMAIL = "mario" + ".rossi@example.org"


@pytest.fixture
def flusso() -> Iterator[io.StringIO]:
    """Righe JSON scritte sul logger radice durante il test."""
    scritto = io.StringIO()
    gestore = logging.StreamHandler(scritto)
    gestore.setFormatter(FormatoJson())
    radice = logging.getLogger()
    livello = radice.level
    radice.addHandler(gestore)
    radice.setLevel(logging.INFO)
    yield scritto
    radice.removeHandler(gestore)
    radice.setLevel(livello)


def _app() -> FastAPI:
    app = crea_app()

    @app.get("/esplodi/{codice}")
    def esplodi(codice: str) -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError(f"email={EMAIL} {codice}")

    return app


def test_risposta_restituisce_id_ricevuto() -> None:
    risposta = TestClient(crea_app()).get("/health", headers={"X-Request-Id": "abc-123"})

    assert risposta.headers["X-Request-Id"] == "abc-123"


@pytest.mark.parametrize("ricevuto", [None, "", "a b", "x" * 65, 'inietta"\n{'])
def test_id_generato_se_manca_o_non_sicuro(ricevuto: str | None) -> None:
    generato = nuovo_id(ricevuto)

    assert generato != ricevuto
    assert len(generato) == 32


def test_riga_per_richiesta_con_rotta_non_percorso() -> None:
    flusso = io.StringIO()
    gestore = logging.StreamHandler(flusso)
    gestore.setFormatter(FormatoJson())
    logger = logging.getLogger("academy_hub.richieste")
    logger.addHandler(gestore)
    logger.setLevel(logging.INFO)
    try:
        TestClient(_app(), raise_server_exceptions=False).get(
            "/esplodi/segreto?token=abc", headers={"X-Request-Id": "r1"}
        )
    finally:
        logger.removeHandler(gestore)

    riga = json.loads(flusso.getvalue().splitlines()[-1])
    assert riga["request_id"] == "r1"
    assert riga["metodo"] == "GET"
    assert riga["rotta"] == "/esplodi/{codice}"
    assert riga["stato"] == 500
    assert isinstance(riga["durata_ms"], float)
    assert "segreto" not in flusso.getvalue()
    assert "token" not in flusso.getvalue()


def test_errore_500_porta_id_e_nessun_dato_personale(flusso: io.StringIO) -> None:
    risposta = TestClient(_app(), raise_server_exceptions=False).get(
        "/esplodi/x", headers={"X-Request-Id": "r500"}
    )
    testo = flusso.getvalue()
    righe: list[dict[str, object]] = [json.loads(r) for r in testo.splitlines()]

    assert risposta.status_code == 500
    assert risposta.headers["X-Request-Id"] == "r500"
    assert "mario.rossi" not in testo
    errori = [r for r in righe if r["livello"] == "ERROR"]
    assert errori
    assert all(r.get("request_id") == "r500" for r in errori)
    assert any(r.get("eccezione") == "RuntimeError" for r in errori)


def test_formato_json_campi_ed_eccezione_senza_messaggio() -> None:
    try:
        raise ValueError(f"Key (email)=({EMAIL}) already exists")
    except ValueError:
        record = logging.getLogger("prova").makeRecord(
            "prova", logging.ERROR, __file__, 1, "fallito %s", ("x",), exc_info=sys.exc_info()
        )
    record.campi = {"edizione_id": 7}
    token = id_richiesta.set("rid")
    try:
        riga = json.loads(FormatoJson().format(record))
    finally:
        id_richiesta.reset(token)

    assert riga["messaggio"] == "fallito x"
    assert riga["livello"] == "ERROR"
    assert riga["request_id"] == "rid"
    assert riga["edizione_id"] == 7
    assert riga["eccezione"] == "ValueError"
    assert "test_formato_json" in riga["stack"]
    assert "mario.rossi" not in json.dumps(riga)
