"""Build statica del frontend servita dallo stesso processo dell'API (ADR-0001, ADR-0009 §14).

Con `ACADEMY_FRONTEND_DIR` l'app serve `assets/` e i file della radice della build;
ogni altra GET fuori dall'API riceve `index.html`, così un refresh su una rotta del
client (`/gestione/edizioni/3`) carica la SPA. L'API resta JSON anche quando sbaglia.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from academy_hub.config import Impostazioni, impostazioni
from academy_hub.main import crea_app

INDICE = "<!doctype html><title>Academy Hub</title>"
SEGRETO = "non deve uscire"


@pytest.fixture
def build(tmp_path: Path) -> Path:
    # Un file accanto alla build: nessuna richiesta deve poterlo leggere.
    (tmp_path / "segreto.txt").write_text(SEGRETO, encoding="utf-8")
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDICE, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return dist


@pytest.fixture
def client(build: Path) -> Iterator[TestClient]:
    with TestClient(crea_app(frontend=build)) as client:
        yield client


@pytest.mark.parametrize("percorso", ["/", "/iscrizioni", "/gestione/edizioni/3"])
def test_rotte_del_client_ricevono_index(client: TestClient, percorso: str) -> None:
    risposta = client.get(percorso)

    assert risposta.status_code == 200
    assert risposta.text == INDICE
    assert risposta.headers["Content-Type"].startswith("text/html")
    # index.html punta agli asset con l'hash della build: non deve restare in cache.
    assert risposta.headers["Cache-Control"] == "no-cache"


def test_index_con_intestazioni_di_sicurezza(client: TestClient) -> None:
    """Il token sta in sessionStorage: un XSS varrebbe una sessione (threat model)."""
    intestazioni = client.get("/").headers

    csp = intestazioni["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Il browser parla con Keycloak (discovery, token): l'origine dell'emittente.
    assert "connect-src 'self' http://localhost:8080" in csp
    assert intestazioni["X-Content-Type-Options"] == "nosniff"
    assert intestazioni["Referrer-Policy"] == "no-referrer"


def test_head_sulle_rotte_del_client(client: TestClient) -> None:
    risposta = client.head("/iscrizioni")

    assert risposta.status_code == 200
    assert risposta.content == b""


def test_asset_con_hash_in_cache_per_sempre(client: TestClient) -> None:
    risposta = client.get("/assets/index-abc123.js")

    assert risposta.status_code == 200
    assert risposta.text == "console.log(1)"
    assert risposta.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert risposta.headers["X-Content-Type-Options"] == "nosniff"


def test_file_della_radice_della_build(client: TestClient) -> None:
    risposta = client.get("/favicon.svg")

    assert risposta.status_code == 200
    assert risposta.text == "<svg/>"


def test_asset_mancante_404_non_index(client: TestClient) -> None:
    """Un chunk vecchio dopo un rilascio deve fallire, non diventare HTML eseguito come JS."""
    risposta = client.get("/assets/index-vecchio.js")

    assert risposta.status_code == 404
    assert risposta.headers["Content-Type"] == "application/problem+json"


@pytest.mark.parametrize("percorso", ["/api", "/api/v1/inesistente", "/api/v2/catalogo"])
@pytest.mark.parametrize("metodo", ["GET", "HEAD", "POST", "DELETE"])
def test_api_inesistente_resta_404(client: TestClient, metodo: str, percorso: str) -> None:
    """Sotto /api il fallback non c'è: un percorso sconosciuto non dichiara metodi (405)."""
    risposta = client.request(metodo, percorso)

    assert risposta.status_code == 404
    assert risposta.headers["Content-Type"] == "application/problem+json"


def test_metodo_sbagliato_su_rotta_api_resta_405(client: TestClient) -> None:
    assert client.delete("/api/v1/catalogo").status_code == 405


def test_rotte_di_sistema_non_coperte(client: TestClient) -> None:
    assert client.get("/health").json()["stato"] == "ok"
    assert client.get("/openapi.json").json()["info"]["title"] == "Academy Hub"
    assert "swagger" in client.get("/docs").text.lower()


@pytest.mark.parametrize(
    "percorso",
    [
        "/..%2fsegreto.txt",
        "/%2e%2e/segreto.txt",
        "/assets/..%2f..%2fsegreto.txt",
        "/assets/%2e%2e/%2e%2e/segreto.txt",
    ],
)
def test_niente_file_fuori_dalla_build(client: TestClient, percorso: str) -> None:
    assert SEGRETO not in client.get(percorso).text


def test_niente_percorso_assoluto(client: TestClient, build: Path) -> None:
    """`radice / "/assoluto"` darebbe il percorso assoluto: deve restare fuori."""
    segreto = (build.parent / "segreto.txt").resolve().as_posix()
    # "//x" nell'URL sarebbe un host: la barra iniziale del percorso va codificata.
    # Su Windows il percorso assoluto inizia con il disco ("C:/..."), senza barra.
    url = "/%2F" + segreto[1:] if segreto.startswith("/") else "/" + segreto

    assert SEGRETO not in client.get(url).text


def test_niente_collegamento_verso_fuori(build: Path) -> None:
    try:
        os.symlink(build.parent / "segreto.txt", build / "collegamento.txt")
    except OSError:
        pytest.skip("symlink non permessi (Windows senza modalità sviluppatore)")
    client = TestClient(crea_app(frontend=build))

    assert SEGRETO not in client.get("/collegamento.txt").text


@pytest.mark.parametrize("percorso", ["/%00", "/a%00b", "/assets/%00.js"])
def test_carattere_nullo_404_non_500(client: TestClient, percorso: str) -> None:
    """Path.resolve() solleva ValueError: senza controllo chiunque produce 500 e log d'errore."""
    risposta = client.get(percorso)

    assert risposta.status_code == 404


def test_post_su_rotta_del_client_non_ammesso(client: TestClient) -> None:
    risposta = client.post("/gestione")

    assert risposta.status_code == 405


def test_rotte_statiche_fuori_dal_contratto(build: Path) -> None:
    """Il contratto OpenAPI non cambia se l'app serve anche il frontend."""
    assert crea_app(frontend=build).openapi() == crea_app().openapi()


def test_senza_build_solo_api() -> None:
    client = TestClient(crea_app())

    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200


def test_build_senza_index_non_parte(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"index\.html"):
        crea_app(frontend=tmp_path)


def test_cartella_dalla_variabile(monkeypatch: pytest.MonkeyPatch, build: Path) -> None:
    monkeypatch.setenv("ACADEMY_FRONTEND_DIR", str(build))
    impostazioni.cache_clear()
    try:
        assert Impostazioni().frontend_dir == build
        assert TestClient(crea_app()).get("/iscrizioni").text == INDICE
    finally:
        impostazioni.cache_clear()
