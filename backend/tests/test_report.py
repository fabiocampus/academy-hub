"""Report letti da Unity Catalog con l'identità dell'utente (issue #73, ADR-0011).

L'adapter Databricks si prova con un trasporto finto che risponde come la Statement
Execution API (forme prese da risposte vere del workspace): la lettura vera, con il
token dell'utente, si prova con il deploy su collaudo.
"""

from typing import Any

import pytest

from academy_hub.config import Impostazioni
from academy_hub.dominio.errori import AzioneNonConsentita, NonAutenticato
from academy_hub.report import (
    NessunReport,
    ReportDatabricks,
    ReportIscrizioniPerCorso,
    ReportNonAutorizzato,
    ReportNonDisponibile,
    RigaIscrizioniPerCorso,
    lettore_report,
)

COLONNE = ("letto_come", "corso_id", "titolo", "edizioni", "confermate", "in_attesa")


def _riuscita(righe: list[list[str | None]], colonne: tuple[str, ...] = COLONNE) -> dict[str, Any]:
    return {
        "statement_id": "01f0-finto",
        "status": {"state": "SUCCEEDED"},
        "manifest": {
            "format": "JSON_ARRAY",
            "schema": {
                "column_count": len(colonne),
                "columns": [{"name": c, "position": i} for i, c in enumerate(colonne)],
            },
            "total_row_count": len(righe),
        },
        "result": {"data_array": righe} if righe else {},
    }


def _fallita(codice: str, messaggio: str) -> dict[str, Any]:
    return {
        "statement_id": "01f0-finto",
        "status": {"state": "FAILED", "error": {"error_code": codice, "message": messaggio}},
    }


class Trasporto:
    """Registra le chiamate e risponde con lo stato HTTP e il corpo dati."""

    def __init__(self, stato: int, corpo: dict[str, Any]) -> None:
        self.stato = stato
        self.corpo = corpo
        self.chiamate: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, token: str, richiesta: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.chiamate.append((token, richiesta))
        return self.stato, self.corpo


def _lettore(trasporto: Trasporto) -> ReportDatabricks:
    return ReportDatabricks(
        warehouse_id="9f8eb48fc8353aa1", catalogo="academy_collaudo", invia=trasporto
    )


def test_legge_il_report_con_il_token_dell_utente() -> None:
    trasporto = Trasporto(
        200,
        _riuscita(
            [
                ["anna@esempio.test", "2", "Python per l'analisi dei dati", "3", "12", "4"],
                ["anna@esempio.test", "1", "SQL avanzato", "1", "5", "0"],
            ]
        ),
    )

    report = _lettore(trasporto).iscrizioni_per_corso("token-di-anna")

    assert report == ReportIscrizioniPerCorso(
        letto_come="anna@esempio.test",
        righe=[
            RigaIscrizioniPerCorso(2, "Python per l'analisi dei dati", 3, 12, 4),
            RigaIscrizioniPerCorso(1, "SQL avanzato", 1, 5, 0),
        ],
    )
    [(token, richiesta)] = trasporto.chiamate
    assert token == "token-di-anna"  # noqa: S105 (finto)
    # Catalogo e schema come parametri della richiesta, non dentro il testo SQL.
    assert richiesta["warehouse_id"] == "9f8eb48fc8353aa1"
    assert richiesta["catalog"] == "academy_collaudo"
    assert richiesta["schema"] == "gold"
    assert "academy_collaudo" not in richiesta["statement"]
    assert richiesta["on_wait_timeout"] == "CANCEL"


def test_report_vuoto() -> None:
    report = _lettore(Trasporto(200, _riuscita([]))).iscrizioni_per_corso("t")

    assert report == ReportIscrizioniPerCorso(letto_come=None, righe=[])


def test_senza_token_dell_utente_il_report_non_e_disponibile() -> None:
    """Senza lo scope `sql` (user_api_scopes) la piattaforma non manda il token."""
    trasporto = Trasporto(200, _riuscita([]))

    with pytest.raises(ReportNonDisponibile):
        _lettore(trasporto).iscrizioni_per_corso(None)
    assert trasporto.chiamate == []


@pytest.mark.parametrize(
    ("codice", "messaggio"),
    [
        ("PERMISSION_DENIED", "User does not have SELECT on Table 'academy_collaudo.gold.x'."),
        (
            "BAD_REQUEST",
            "[INSUFFICIENT_PERMISSIONS] Insufficient privileges:\nUser does not have USE SCHEMA "
            "on Schema 'academy_collaudo.gold'.",
        ),
    ],
)
def test_unity_catalog_nega_la_lettura(codice: str, messaggio: str) -> None:
    """Decide Unity Catalog con i permessi dell'utente: l'App riporta il rifiuto (403)."""
    with pytest.raises(ReportNonAutorizzato) as errore:
        _lettore(Trasporto(200, _fallita(codice, messaggio))).iscrizioni_per_corso("t")

    assert isinstance(errore.value, AzioneNonConsentita)


def test_tabella_mancante_non_e_disponibile() -> None:
    messaggio = (
        "[TABLE_OR_VIEW_NOT_FOUND] The table or view `iscrizioni_per_corso` cannot be found."
    )

    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(200, _fallita("BAD_REQUEST", messaggio))).iscrizioni_per_corso("t")


@pytest.mark.parametrize("stato", ["PENDING", "RUNNING", "CANCELED", "CLOSED"])
def test_warehouse_che_non_finisce_in_tempo(stato: str) -> None:
    corpo = {"statement_id": "x", "status": {"state": stato}}

    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(200, corpo)).iscrizioni_per_corso("t")


def test_token_rifiutato_da_databricks_e_non_autenticato() -> None:
    corpo = {"error_code": "UNAUTHENTICATED", "message": "Invalid access token."}

    with pytest.raises(NonAutenticato):
        _lettore(Trasporto(401, corpo)).iscrizioni_per_corso("t")


def test_warehouse_negato_all_utente() -> None:
    """403 HTTP: l'utente non può usare il warehouse, o il token non ha lo scope sql."""
    corpo = {"error_code": "PERMISSION_DENIED", "message": "no CAN_USE"}

    with pytest.raises(ReportNonAutorizzato):
        _lettore(Trasporto(403, corpo)).iscrizioni_per_corso("t")


@pytest.mark.parametrize("stato", [400, 404, 429, 500, 503])
def test_altri_errori_http_non_disponibile(stato: int) -> None:
    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(stato, {"message": "boh"})).iscrizioni_per_corso("t")


def test_colonne_inattese_non_disponibile() -> None:
    """La tabella gold è cambiata: meglio un 503 che dati messi nei campi sbagliati."""
    corpo = _riuscita([["a", "1", "x", "1", "1"]], COLONNE[:-1])

    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(200, corpo)).iscrizioni_per_corso("t")


def test_il_token_non_finisce_nei_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    corpo = _fallita("BAD_REQUEST", "[TABLE_OR_VIEW_NOT_FOUND] manca")

    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(200, corpo)).iscrizioni_per_corso("segreto-123")

    assert "segreto-123" not in caplog.text


def test_senza_configurazione_nessun_report() -> None:
    with pytest.raises(ReportNonDisponibile):
        NessunReport().iscrizioni_per_corso("t")


def test_lettore_dalla_configurazione() -> None:
    assert isinstance(lettore_report(Impostazioni(ambiente="locale")), NessunReport)
    configurato = Impostazioni(
        ambiente="collaudo",
        identita="databricks",
        report_warehouse_id="9f8eb48fc8353aa1",
        report_catalogo="academy_collaudo",
        databricks_host="dbc-esempio.cloud.databricks.com",
    )
    assert isinstance(lettore_report(configurato), ReportDatabricks)


def test_report_configurato_a_meta_e_un_errore() -> None:
    with pytest.raises(ValueError, match="report"):
        Impostazioni(ambiente="locale", report_warehouse_id="9f8eb48fc8353aa1")
