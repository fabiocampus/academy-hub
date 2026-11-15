"""Report letti da Unity Catalog con l'identità dell'utente (issue #73, ADR-0011).

L'adapter Databricks si prova con un trasporto finto che risponde come la Statement
Execution API (forme prese da risposte vere del workspace): la lettura vera, con il
token dell'utente, si prova con il deploy su collaudo.
"""

from typing import Any

import pytest

from academy_hub.config import Impostazioni
from academy_hub.dominio.errori import (
    AzioneNonConsentita,
    ReportNonAutorizzato,
    ReportNonDisponibile,
)
from academy_hub.report import (
    ORE_PER_TEAM,
    TASSO_COMPLETAMENTO,
    VALUTAZIONE_MEDIA,
    NessunReport,
    ReportDatabricks,
    ReportIscrizioniPerCorso,
    RigaIscrizioniPerCorso,
    RigaOrePerTeam,
    RigaTassoCompletamento,
    RigaValutazioneMedia,
    invio_http,
    lettore_report,
    sessione_senza_cookie,
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
        warehouse_id="0123456789abcdef", catalogo="academy_collaudo", invia=trasporto
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
    assert richiesta["warehouse_id"] == "0123456789abcdef"
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


def test_token_rifiutato_a_valle_non_e_un_401_dell_app() -> None:
    """L'utente è autenticato presso l'App: un 401 farebbe rifare il login per niente."""
    corpo = {"error_code": "UNAUTHENTICATED", "message": "Invalid access token."}

    with pytest.raises(ReportNonDisponibile):
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


@pytest.mark.parametrize(
    ("stato", "corpo"),
    [
        (200, _fallita("BAD_REQUEST", "[TABLE_OR_VIEW_NOT_FOUND] manca")),
        (200, _fallita("PERMISSION_DENIED", "no")),
        (200, {"status": {"state": "RUNNING"}}),
        (200, _riuscita([["a", "x", "t", "1", "1", "1"]])),
        (200, _riuscita([["a", "1"]], COLONNE[:2])),
        (401, {"error_code": "UNAUTHENTICATED"}),
        (403, {"error_code": "PERMISSION_DENIED"}),
        (500, {}),
    ],
)
def test_il_token_non_finisce_nei_log_ne_nei_messaggi(
    caplog: pytest.LogCaptureFixture, stato: int, corpo: dict[str, Any]
) -> None:
    caplog.set_level("DEBUG")

    with pytest.raises(Exception) as errore:
        _lettore(Trasporto(stato, corpo)).iscrizioni_per_corso("segreto-123")

    assert "segreto-123" not in caplog.text
    assert "segreto-123" not in str(errore.value)


@pytest.mark.parametrize(
    "riga",
    [
        ["a", "abc", "t", "1", "1", "1"],
        ["a", "1", "t", "1.5", "1", "1"],
        ["a", "1", "t"],
    ],
)
def test_valori_non_validi_non_disponibile(riga: list[str | None]) -> None:
    with pytest.raises(ReportNonDisponibile):
        _lettore(Trasporto(200, _riuscita([riga]))).iscrizioni_per_corso("t")


def test_i_messaggi_non_riportano_dettagli_interni() -> None:
    """D10: classi d'errore di Spark e stati HTTP del warehouse solo nel log."""
    corpo = _fallita("BAD_REQUEST", "[TABLE_OR_VIEW_NOT_FOUND] `academy_collaudo`.`gold`.`x`")

    with pytest.raises(ReportNonDisponibile) as errore:
        _lettore(Trasporto(200, corpo)).iscrizioni_per_corso("t")

    assert "TABLE_OR_VIEW_NOT_FOUND" not in str(errore.value)
    assert "academy_collaudo" not in str(errore.value)


class RispostaFinta:
    def __init__(self, stato: int, corpo: object = None, json_valido: bool = True) -> None:
        self.status_code = stato
        self._corpo = corpo
        self._json_valido = json_valido

    def json(self) -> object:
        if not self._json_valido:
            raise ValueError("non JSON")
        return self._corpo


class SessioneFinta:
    def __init__(self, esito: RispostaFinta | Exception) -> None:
        self.esito = esito
        self.chiamate: list[dict[str, Any]] = []

    def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> RispostaFinta:
        self.chiamate.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if isinstance(self.esito, Exception):
            raise self.esito
        return self.esito


@pytest.mark.parametrize(
    "host", ["dbc-esempio.cloud.databricks.com", "https://dbc-esempio.cloud.databricks.com/"]
)
def test_invio_http_manda_il_token_come_bearer(host: str) -> None:
    sessione = SessioneFinta(RispostaFinta(200, {"status": {"state": "SUCCEEDED"}}))

    stato, corpo = invio_http(host, sessione)("token-di-anna", {"statement": "SELECT 1"})

    assert (stato, corpo) == (200, {"status": {"state": "SUCCEEDED"}})
    [chiamata] = sessione.chiamate
    assert chiamata["url"] == "https://dbc-esempio.cloud.databricks.com/api/2.0/sql/statements"
    assert chiamata["headers"] == {"Authorization": "Bearer token-di-anna"}
    assert chiamata["json"] == {"statement": "SELECT 1"}


@pytest.mark.parametrize(
    "risposta", [RispostaFinta(502, json_valido=False), RispostaFinta(200, ["non", "oggetto"])]
)
def test_invio_http_corpo_non_oggetto(risposta: RispostaFinta) -> None:
    stato, corpo = invio_http("h", SessioneFinta(risposta))("t", {})

    assert (stato, corpo) == (risposta.status_code, {})


def test_invio_http_warehouse_irraggiungibile(caplog: pytest.LogCaptureFixture) -> None:
    import requests

    caplog.set_level("DEBUG")
    guasto = requests.ConnectionError("Authorization: Bearer segreto-123")

    with pytest.raises(ReportNonDisponibile):
        invio_http("h", SessioneFinta(guasto))("segreto-123", {})

    assert "segreto-123" not in caplog.text


def test_la_sessione_condivisa_non_tiene_cookie() -> None:
    """Condivisa fra gli utenti: un cookie della risposta per uno non va all'altro."""
    from http.cookiejar import Cookie

    import requests

    sessione = sessione_senza_cookie()
    assert isinstance(sessione, requests.Session)
    richiesta = requests.Request("POST", "https://dbc-esempio.cloud.databricks.com/api").prepare()
    cookie = Cookie(
        0,
        "sessione",
        "di-anna",
        None,
        False,
        "dbc-esempio.cloud.databricks.com",
        True,
        False,
        "/",
        True,
        True,
        None,
        False,
        None,
        None,
        {},
    )

    sessione.cookies.set_cookie_if_ok(cookie, requests.cookies.MockRequest(richiesta))  # type: ignore[attr-defined]

    assert len(sessione.cookies) == 0


def test_senza_configurazione_nessun_report() -> None:
    with pytest.raises(ReportNonDisponibile):
        NessunReport().iscrizioni_per_corso("t")


def test_lettore_dalla_configurazione() -> None:
    assert isinstance(lettore_report(Impostazioni(ambiente="locale")), NessunReport)
    configurato = Impostazioni(
        ambiente="collaudo",
        identita="databricks",
        report_warehouse_id="0123456789abcdef",
        report_catalogo="academy_collaudo",
        databricks_host="dbc-esempio.cloud.databricks.com",
    )
    assert isinstance(lettore_report(configurato), ReportDatabricks)


def test_report_configurato_a_meta_e_un_errore() -> None:
    with pytest.raises(ValueError, match="report"):
        Impostazioni(ambiente="locale", report_warehouse_id="0123456789abcdef")


def test_gold_ore_per_team() -> None:
    trasporto = Trasporto(
        200, _riuscita([["anna@esempio.test", "7", None, "16", "2"]], ORE_PER_TEAM.colonne)
    )

    report = _lettore(trasporto).gold(ORE_PER_TEAM, "token-di-anna")

    assert report.letto_come == "anna@esempio.test"
    assert report.righe == [RigaOrePerTeam(7, None, 16, 2)]
    token, richiesta = trasporto.chiamate[0]
    assert (token, richiesta["schema"]) == ("token-di-anna", "gold")
    assert "FROM ore_per_team" in richiesta["statement"]


def test_gold_tasso_e_valutazione_decimali() -> None:
    tasso = Trasporto(
        200,
        _riuscita([["a@esempio.test", "1", "SQL", "4", "3", "0.75"]], TASSO_COMPLETAMENTO.colonne),
    )
    voto = Trasporto(
        200, _riuscita([["a@esempio.test", "1", "SQL", "3", "4.33"]], VALUTAZIONE_MEDIA.colonne)
    )

    assert _lettore(tasso).gold(TASSO_COMPLETAMENTO, "t").righe == [
        RigaTassoCompletamento(1, "SQL", 4, 3, 0.75)
    ]
    assert _lettore(voto).gold(VALUTAZIONE_MEDIA, "t").righe == [
        RigaValutazioneMedia(1, "SQL", 3, 4.33)
    ]


def test_gold_vuoto_colonne_inattese_e_valori_non_validi() -> None:
    vuoto = _lettore(Trasporto(200, _riuscita([], ORE_PER_TEAM.colonne)))
    assert vuoto.gold(ORE_PER_TEAM, "t").righe == []
    with pytest.raises(ReportNonDisponibile, match="colonne"):
        _lettore(Trasporto(200, _riuscita([], COLONNE))).gold(ORE_PER_TEAM, "t")
    with pytest.raises(ReportNonDisponibile, match="Valori"):
        _lettore(
            Trasporto(200, _riuscita([["a", "x", "Dati", "1", "1"]], ORE_PER_TEAM.colonne))
        ).gold(ORE_PER_TEAM, "t")
    with pytest.raises(ReportNonDisponibile, match="token"):
        vuoto.gold(ORE_PER_TEAM, None)
    with pytest.raises(ReportNonDisponibile):
        NessunReport().gold(ORE_PER_TEAM, "t")
