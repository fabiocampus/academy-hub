"""Matrice di autorizzazione (issue #56): ogni rotta per ogni profilo, con lo stato atteso.

Le identità passano dal token OIDC, come in docker compose: «non registrata» è un token
valido di un'email che non è nel database, «anonimo» non manda niente. Ogni persona ha
un solo ruolo, così la riga mostra che cosa concede quel ruolo e nient'altro.

Il mondo di partenza:

```
Vertice (nessun responsabile)
└── Dati (resp. Rossa): Anna
```

Anna ha una Richiesta (edizione A) e un'Approvata (edizione B); l'edizione C è libera.
Il responsabile non è un ruolo che apre rotte: decide chi è `responsabile_id` del team
del richiedente (R2); l'amministratore non decide al posto suo.

`test_ogni_rotta_ha_la_sua_riga` fallisce se si aggiunge una rotta senza la riga.
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
from academy_hub.db.modelli import Edizione, Persona
from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import StatoIscrizione
from academy_hub.main import crea_app

from .dati import crea_edizione, crea_iscrizione, crea_persona, crea_team
from .oidc import ProviderFinto

R = Ruolo
S = StatoIscrizione

PROFILI = ("dipendente", "responsabile", "admin_academy", "docente", "non_registrata", "anonimo")
_PERSONE = {
    "dipendente": ("Anna", R.DIPENDENTE),
    "responsabile": ("Rossa", R.RESPONSABILE),
    "admin_academy": ("Admin", R.ADMIN_ACADEMY),
    "docente": ("Dora", R.DOCENTE),
}


@dataclass(frozen=True)
class Mondo:
    corso: int
    edizione_libera: int
    richiesta: int
    approvata: int


@dataclass(frozen=True)
class Chiamata:
    metodo: str
    percorso: str
    corpo: dict[str, Any] | None = None
    intestazioni: dict[str, str] | None = None


Riga = tuple[Callable[[Mondo], Chiamata], dict[str, int]]

_IF_MATCH = {"If-Match": '"1"'}


def _attesi(dip: int, resp: int, admin: int, doc: int) -> dict[str, int]:
    """Stati attesi delle persone registrate; il resto dell'API è chiuso agli sconosciuti."""
    return {
        "dipendente": dip,
        "responsabile": resp,
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
        _attesi(200, 403, 200, 403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/approvazione"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/approvazione"),
        _attesi(403, 200, 403, 403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/rifiuto"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/rifiuto", {"motivo": "No"}),
        _attesi(403, 200, 403, 403),
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/conferma"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.approvata}/conferma"),
        SOLO_ADMIN,
    ),
    ("POST", "/iscrizioni/{iscrizione_id}/annullamento"): (
        lambda m: Chiamata("POST", f"/iscrizioni/{m.richiesta}/annullamento"),
        _attesi(200, 403, 403, 403),
    ),
    ("GET", "/richieste-da-approvare"): (
        lambda m: Chiamata("GET", "/richieste-da-approvare"),
        TUTTI,
    ),
}

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
    for _, attesi in MATRICE.values():
        assert set(attesi) == set(PROFILI)


@pytest.fixture(scope="module")
def provider() -> ProviderFinto:
    return ProviderFinto()


@pytest.fixture
def client(db: Engine, provider: ProviderFinto) -> Iterator[TestClient]:
    with TestClient(crea_app(motore=db, identita=provider.oidc())) as client:
        yield client


@pytest.fixture
def mondo(db: Engine) -> Mondo:
    with Session(db) as sessione:
        vertice = crea_team(sessione, "Vertice")
        dati = crea_team(sessione, "Dati", vertice)
        persone: dict[str, Persona] = {
            profilo: crea_persona(
                sessione,
                nome,
                dati if profilo in {"dipendente", "responsabile"} else vertice,
                (ruolo,),
            )
            for profilo, (nome, ruolo) in _PERSONE.items()
        }
        dati.responsabile_id = persone["responsabile"].id
        anna = persone["dipendente"]
        a, b, c = (crea_edizione(sessione) for _ in range(3))
        richiesta = crea_iscrizione(sessione, anna, a, S.RICHIESTA)
        approvata = crea_iscrizione(sessione, anna, b, S.APPROVATA)
        sessione.commit()
        corso = sessione.get_one(Edizione, c.id).corso_id
        return Mondo(corso, c.id, richiesta.id, approvata.id)


def _identita(provider: ProviderFinto, profilo: str) -> dict[str, str]:
    if profilo == "anonimo":
        return {}
    if profilo == "non_registrata":
        return provider.intestazioni("sconosciuta@esempio.test")
    nome, _ = _PERSONE[profilo]
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
    ("rotta", "profilo"),
    [
        pytest.param(rotta, profilo, id=f"{rotta[0]} {rotta[1]} {profilo}")
        for rotta in MATRICE
        for profilo in PROFILI
    ],
)
def test_matrice(
    client: TestClient,
    provider: ProviderFinto,
    mondo: Mondo,
    rotta: tuple[str, str],
    profilo: str,
) -> None:
    chiamata, attesi = MATRICE[rotta]

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
