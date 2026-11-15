"""Matrice di autorizzazione (issue #56): ogni rotta per ogni profilo, con lo stato atteso.

Le identità passano dal token OIDC, come in docker compose: «non registrata» è un token
valido di un'email che non è nel database, «anonimo» non manda niente. Ogni persona ha
un solo ruolo, così la riga mostra che cosa concede quel ruolo e nient'altro. Per i
controlli sull'oggetto (titolare, responsabile diretto) ci sono un altro dipendente e un
altro responsabile, con lo stesso ruolo ma fuori dal rapporto con l'iscrizione.

Il mondo di partenza:

```
Vertice (nessun responsabile): Vera, Admin, Dora
├── Dati (resp. Rossa): Anna
└── Web  (resp. Verdi): Carla
```

Anna ha una Richiesta (edizione A), un'Approvata (edizione B) e una Confermata (edizione D);
l'edizione C è libera. Le feature flag sono accese (ADR-0014): spente, le rotte rispondono 404.
Vera ha una Richiesta (edizione A): la decide l'amministrazione Academy.
Il responsabile non è un ruolo che apre rotte: decide chi è `responsabile_id` del team
del richiedente (R2); l'amministratore non decide al posto suo.

La matrice controlla gli stati, non il contenuto degli elenchi: quali iscrizioni e quali
richieste vede ciascuno lo verificano `test_api_iscrizioni.py` e `test_api_approvazione.py`.

`test_ogni_rotta_ha_la_sua_riga` fallisce se si aggiunge una rotta senza la riga. Le
rotte vengono dallo schema OpenAPI: una rotta con `include_in_schema=False` sfuggirebbe,
quindi non se ne usano.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from academy_hub.api import PREFISSO
from academy_hub.config import impostazioni
from academy_hub.db.modelli import Edizione, Persona
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.main import crea_app
from academy_hub.report import ReportIscrizioniPerCorso

from .dati import crea_edizione, crea_iscrizione, crea_persona, crea_team
from .oidc import ProviderFinto

R = Ruolo
S = StatoIscrizione

PROFILI = (
    "dipendente",
    "altro_dipendente",
    "responsabile",
    "altro_responsabile",
    "admin_academy",
    "docente",
    "non_registrata",
    "anonimo",
)
# profilo -> (nome, ruolo, team)
_PERSONE = {
    "dipendente": ("Anna", R.DIPENDENTE, "Dati"),
    "altro_dipendente": ("Carla", R.DIPENDENTE, "Web"),
    "responsabile": ("Rossa", R.RESPONSABILE, "Dati"),
    "altro_responsabile": ("Verdi", R.RESPONSABILE, "Web"),
    "admin_academy": ("Admin", R.ADMIN_ACADEMY, "Vertice"),
    "docente": ("Dora", R.DOCENTE, "Vertice"),
}


@dataclass(frozen=True)
class Mondo:
    corso: int
    edizione_libera: int
    richiesta: int
    approvata: int
    richiesta_vertice: int
    confermata: int


@dataclass(frozen=True)
class Chiamata:
    metodo: str
    percorso: str
    corpo: dict[str, Any] | None = None
    intestazioni: dict[str, str] | None = None


Riga = tuple[Callable[[Mondo], Chiamata], dict[str, int]]

_IF_MATCH = {"If-Match": '"1"'}


def _attesi(
    dip: int,
    resp: int,
    admin: int,
    doc: int,
    *,
    altro_dip: int | None = None,
    altro_resp: int | None = None,
) -> dict[str, int]:
    """Stati attesi delle persone registrate; il resto dell'API è chiuso agli sconosciuti.

    Senza indicazioni l'altro dipendente e l'altro responsabile valgono come i primi:
    cambiano solo dove conta il rapporto con l'iscrizione.
    """
    return {
        "dipendente": dip,
        "altro_dipendente": dip if altro_dip is None else altro_dip,
        "responsabile": resp,
        "altro_responsabile": resp if altro_resp is None else altro_resp,
        "admin_academy": admin,
        "docente": doc,
        "non_registrata": 403,
        "anonimo": 401,
    }


TUTTI = _attesi(200, 200, 200, 200)
SOLO_ADMIN = _attesi(403, 403, 200, 403)

MATRICE: dict[tuple[str, str], Riga] = {
    ("GET", "/catalogo"): (lambda m: Chiamata("GET", "/catalogo"), TUTTI),
    ("POST", "/corsi"): (
        lambda m: Chiamata("POST", "/corsi", {"titolo": "Python", "durata_ore": 4}),
        _attesi(403, 403, 201, 403),
    ),
    # Elenchi della gestione Academy (issue #64): solo l'amministrazione.
    ("GET", "/corsi"): (lambda m: Chiamata("GET", "/corsi"), SOLO_ADMIN),
    ("GET", "/corsi/{corso_id}/edizioni"): (
        lambda m: Chiamata("GET", f"/corsi/{m.corso}/edizioni"),
        SOLO_ADMIN,
    ),
    ("GET", "/edizioni/{edizione_id}/iscrizioni"): (
        lambda m: Chiamata("GET", f"/edizioni/{m.edizione_libera}/iscrizioni"),
        SOLO_ADMIN,
    ),
    ("GET", "/docenti"): (lambda m: Chiamata("GET", "/docenti"), SOLO_ADMIN),
    ("GET", "/corsi/{corso_id}"): (lambda m: Chiamata("GET", f"/corsi/{m.corso}"), TUTTI),
    ("PATCH", "/corsi/{corso_id}"): (
        lambda m: Chiamata("PATCH", f"/corsi/{m.corso}", {"titolo": "Nuovo"}, _IF_MATCH),
        SOLO_ADMIN,
    ),
    ("POST", "/corsi/{corso_id}/archiviazione"): (
        lambda m: Chiamata("POST", f"/corsi/{m.corso}/archiviazione", None, _IF_MATCH),
        SOLO_ADMIN,
    ),
    ("POST", "/edizioni"): (
        lambda m: Chiamata(
            "POST",
            "/edizioni",
            {
                "corso_id": m.corso,
                "data_inizio": "2099-01-10",
                "data_fine": "2099-01-11",
                "capienza": 5,
            },
        ),
        _attesi(403, 403, 201, 403),
    ),
    ("GET", "/edizioni/{edizione_id}"): (
        lambda m: Chiamata("GET", f"/edizioni/{m.edizione_libera}"),
        TUTTI,
    ),
    ("PATCH", "/edizioni/{edizione_id}"): (
        lambda m: Chiamata("PATCH", f"/edizioni/{m.edizione_libera}", {"capienza": 20}, _IF_MATCH),
        SOLO_ADMIN,
    ),
    ("POST", "/edizioni/{edizione_id}/cancellazione"): (
        lambda m: Chiamata("POST", f"/edizioni/{m.edizione_libera}/cancellazione"),
        SOLO_ADMIN,
    ),
    ("POST", "/iscrizioni"): (
        lambda m: Chiamata("POST", "/iscrizioni", {"edizione_id": m.edizione_libera}),
        _attesi(201, 403, 403, 403),
    ),
    ("GET", "/iscrizioni"): (lambda m: Chiamata("GET", "/iscrizioni"), TUTTI),
    ("GET", "/iscrizioni/{iscrizione_id}"): (
        lambda m: Chiamata("GET", f"/iscrizioni/{m.richiesta}"),
        _attesi(200, 403, 200, 403, altro_dip=403),
    ),
    # Feature flag del calendario (ADR-0014): solo il titolare di una Confermata.
    ("GET", "/iscrizioni/{iscrizione_id}/calendario.ics"): (
        lambda m: Chiamata("GET", f"/iscrizioni/{m.confermata}/calendario.ics"),
        _attesi(200, 403, 403, 403, altro_dip=403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/approvazione"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/approvazione"),
        _attesi(403, 200, 403, 403, altro_resp=403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/rifiuto"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/rifiuto", {"motivo": "No"}),
        _attesi(403, 200, 403, 403, altro_resp=403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/conferma"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.approvata}/conferma"),
        SOLO_ADMIN,
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/annullamento"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/annullamento"),
        _attesi(200, 403, 403, 403, altro_dip=403),
    ),
    ("GET", "/richieste-da-approvare"): (
        lambda m: Chiamata("GET", "/richieste-da-approvare"),
        TUTTI,
    ),
    ("GET", "/io"): (lambda m: Chiamata("GET", "/io"), TUTTI),
    # Basta essere registrati: chi legge la tabella lo decide Unity Catalog (ADR-0011).
    ("GET", "/report/iscrizioni-per-corso"): (
        lambda m: Chiamata("GET", "/report/iscrizioni-per-corso"),
        TUTTI,
    ),
    # Pubblica: il frontend la legge prima del login.
    ("GET", "/configurazione"): (
        lambda m: Chiamata("GET", "/configurazione"),
        TUTTI | {"non_registrata": 200, "anonimo": 200},
    ),
}

# Altri casi di rotte già nella matrice, dove cambia chi può.
VARIANTI: dict[str, Riga] = {
    "approvazione di una richiesta dal vertice": (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta_vertice}/approvazione"),
        SOLO_ADMIN,
    ),
    "rifiuto di una richiesta dal vertice": (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta_vertice}/rifiuto", {"motivo": "No"}),
        SOLO_ADMIN,
    ),
}

CASI: dict[str, Riga] = {f"{m} {p}": riga for (m, p), riga in MATRICE.items()} | VARIANTI

# Fuori dal prefisso dell'API, aperta a tutti: la usano i controlli di salute.
PUBBLICHE: dict[tuple[str, str], Callable[[Mondo], Chiamata]] = {
    ("GET", "/health"): lambda m: Chiamata("GET", "/health"),
}


def test_ogni_rotta_ha_la_sua_riga() -> None:
    """Una rotta nuova senza riga nella matrice fa fallire questo test."""
    app = crea_app(
        motore=create_engine("postgresql+psycopg://nessuno@127.0.0.1/nessuno"),
        identita=ProviderFinto().oidc(),
    )
    rotte = {
        (metodo.upper(), percorso)
        for percorso, operazioni in app.openapi()["paths"].items()
        for metodo in operazioni
    }
    attese = {(m, PREFISSO + p) for m, p in MATRICE} | set(PUBBLICHE)

    assert rotte == attese


def test_ogni_riga_copre_ogni_profilo() -> None:
    for _, attesi in CASI.values():
        assert set(attesi) == set(PROFILI)


@pytest.fixture(scope="module")
def provider() -> ProviderFinto:
    return ProviderFinto()


@pytest.fixture
def client(
    db: Engine, provider: ProviderFinto, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("ACADEMY_FLAG_CALENDARIO", "true")
    impostazioni.cache_clear()
    report = ReportIscrizioniPerCorso(letto_come=None, righe=[])

    class Lettore:
        def iscrizioni_per_corso(self, token_utente: str | None) -> ReportIscrizioniPerCorso:
            return report

    try:
        with TestClient(crea_app(motore=db, identita=provider.oidc(), report=Lettore())) as client:
            yield client
    finally:
        impostazioni.cache_clear()


@pytest.fixture
def mondo(db: Engine) -> Mondo:
    with Session(db) as sessione:
        vertice = crea_team(sessione, "Vertice")
        team = {
            "Vertice": vertice,
            "Dati": crea_team(sessione, "Dati", vertice),
            "Web": crea_team(sessione, "Web", vertice),
        }
        persone: dict[str, Persona] = {
            profilo: crea_persona(sessione, nome, team[nome_team], (ruolo,))
            for profilo, (nome, ruolo, nome_team) in _PERSONE.items()
        }
        team["Dati"].responsabile_id = persone["responsabile"].id
        team["Web"].responsabile_id = persone["altro_responsabile"].id
        anna = persone["dipendente"]
        vera = crea_persona(sessione, "Vera", vertice, (R.DIPENDENTE,))
        a, b, c, d = (crea_edizione(sessione) for _ in range(4))
        richiesta = crea_iscrizione(sessione, anna, a, S.RICHIESTA)
        approvata = crea_iscrizione(sessione, anna, b, S.APPROVATA)
        richiesta_vertice = crea_iscrizione(sessione, vera, a, S.RICHIESTA)
        d.posti_confermati = 1
        confermata = crea_iscrizione(sessione, anna, d, S.CONFERMATA)
        sessione.commit()
        corso = sessione.get_one(Edizione, c.id).corso_id
        return Mondo(corso, c.id, richiesta.id, approvata.id, richiesta_vertice.id, confermata.id)


def _identita(provider: ProviderFinto, profilo: str) -> dict[str, str]:
    if profilo == "anonimo":
        return {}
    if profilo == "non_registrata":
        return provider.intestazioni("sconosciuta@esempio.test")
    nome, _, _ = _PERSONE[profilo]
    return provider.intestazioni(f"{nome.lower()}@esempio.test")


def _esegui(
    client: TestClient, provider: ProviderFinto, profilo: str, chiamata: Chiamata, prefisso: str
) -> httpx.Response:
    return client.request(
        chiamata.metodo,
        prefisso + chiamata.percorso,
        json=chiamata.corpo,
        headers={**(chiamata.intestazioni or {}), **_identita(provider, profilo)},
    )


@pytest.mark.integrazione
@pytest.mark.parametrize(
    ("caso", "profilo"),
    [pytest.param(caso, profilo, id=f"{caso} {profilo}") for caso in CASI for profilo in PROFILI],
)
def test_matrice(
    client: TestClient,
    provider: ProviderFinto,
    mondo: Mondo,
    caso: str,
    profilo: str,
) -> None:
    chiamata, attesi = CASI[caso]

    risposta = _esegui(client, provider, profilo, chiamata(mondo), PREFISSO)

    assert risposta.status_code == attesi[profilo], risposta.text
    if risposta.status_code == 401:
        assert risposta.headers["WWW-Authenticate"].startswith("Bearer")
    if risposta.status_code in {401, 403}:
        assert risposta.headers["content-type"] == "application/problem+json"


@pytest.mark.integrazione
@pytest.mark.parametrize("rotta", [pytest.param(r, id=" ".join(r)) for r in PUBBLICHE])
@pytest.mark.parametrize("profilo", PROFILI)
def test_rotte_pubbliche(
    client: TestClient, provider: ProviderFinto, mondo: Mondo, rotta: tuple[str, str], profilo: str
) -> None:
    risposta = _esegui(client, provider, profilo, PUBBLICHE[rotta](mondo), "")

    assert risposta.status_code == 200
