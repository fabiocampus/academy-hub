"""GET /report/iscrizioni-per-corso (issue #73, ADR-0011): il token dell'utente arriva al
lettore così com'è, gli errori del lettore diventano problemi RFC 9457."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.api import PREFISSO
from academy_hub.api.identita import Databricks
from academy_hub.main import crea_app
from academy_hub.report import (
    ReportIscrizioniPerCorso,
    ReportNonAutorizzato,
    ReportNonDisponibile,
    RigaIscrizioniPerCorso,
)

from .api import R
from .dati import crea_persona

URL = f"{PREFISSO}/report/iscrizioni-per-corso"
REPORT = ReportIscrizioniPerCorso(
    letto_come="anna@esempio.test",
    righe=[RigaIscrizioniPerCorso(2, "SQL avanzato", 1, 5, 0)],
)


class LettoreFinto:
    def __init__(self, esito: ReportIscrizioniPerCorso | Exception = REPORT) -> None:
        self.esito = esito
        self.token: list[str | None] = []

    def iscrizioni_per_corso(self, token_utente: str | None) -> ReportIscrizioniPerCorso:
        self.token.append(token_utente)
        if isinstance(self.esito, Exception):
            raise self.esito
        return self.esito


@pytest.fixture
def lettore() -> LettoreFinto:
    return LettoreFinto()


@pytest.fixture
def client(db: Engine, lettore: LettoreFinto) -> Iterator[TestClient]:
    """Come su Databricks Apps: identità da X-Forwarded-Email, token in X-Forwarded-Access-Token."""
    with Session(db) as sessione:
        crea_persona(sessione, "Anna", ruoli=(R.DIPENDENTE,))
        sessione.commit()
    with TestClient(crea_app(motore=db, identita=Databricks(), report=lettore)) as client:
        yield client


ANNA = {"X-Forwarded-Email": "anna@esempio.test", "X-Forwarded-Access-Token": "token-di-anna"}


@pytest.mark.integrazione
def test_report_letto_con_il_token_dell_utente(client: TestClient, lettore: LettoreFinto) -> None:
    risposta = client.get(URL, headers=ANNA)

    assert risposta.status_code == 200
    assert risposta.json() == {
        "letto_come": "anna@esempio.test",
        "righe": [
            {
                "corso_id": 2,
                "titolo": "SQL avanzato",
                "edizioni": 1,
                "confermate": 5,
                "in_attesa": 0,
            }
        ],
    }
    assert lettore.token == ["token-di-anna"]
    assert risposta.headers["cache-control"] == "no-store"


@pytest.mark.integrazione
def test_senza_identita_401_e_il_lettore_non_parte(
    client: TestClient, lettore: LettoreFinto
) -> None:
    assert client.get(URL, headers={"X-Forwarded-Access-Token": "t"}).status_code == 401
    assert lettore.token == []


@pytest.mark.integrazione
def test_persona_non_registrata_403(client: TestClient, lettore: LettoreFinto) -> None:
    risposta = client.get(URL, headers={"X-Forwarded-Email": "ignota@esempio.test"})

    assert risposta.status_code == 403
    assert lettore.token == []


@pytest.mark.integrazione
@pytest.mark.parametrize(
    ("errore", "stato", "tipo"),
    [
        (ReportNonAutorizzato("Unity Catalog nega"), 403, "report-non-autorizzato"),
        (ReportNonDisponibile("warehouse spento"), 503, "report-non-disponibile"),
    ],
)
def test_errori_del_lettore_come_problemi(
    client: TestClient, lettore: LettoreFinto, errore: Exception, stato: int, tipo: str
) -> None:
    lettore.esito = errore

    risposta = client.get(URL, headers=ANNA)

    assert risposta.status_code == stato
    assert risposta.headers["content-type"] == "application/problem+json"
    assert risposta.json()["type"] == f"/problemi/{tipo}"
