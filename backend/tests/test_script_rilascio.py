"""Script del rilascio continuo (ADR-0013): `prepara_app.rilascio` e `fumo_rilascio.attendi_health`.

Gli script stanno in `scripts/` (solo libreria standard, fuori dal pacchetto): si caricano
dal file con importlib. Rete, git e orologio sono sostituiti con monkeypatch.
"""

import importlib.util
import json
import re
import types
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SHA = "0123456789abcdef0123456789abcdef01234567"
VECCHIO = "fedcba9876543210fedcba9876543210fedcba98"


def carica(nome: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"script_{nome}", SCRIPTS / f"{nome}.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def prepara() -> types.ModuleType:
    return carica("prepara_app")


@pytest.fixture
def fumo() -> types.ModuleType:
    return carica("fumo_rilascio")


# --- prepara_app.rilascio ---------------------------------------------------------


def git_finto(stato: str, head: str = SHA) -> Callable[[list[str], Path], str]:
    def esegui(comando: list[str], _cartella: Path) -> str:
        if comando[:2] == ["git", "status"]:
            return stato
        if comando[:2] == ["git", "rev-parse"]:
            return head + "\n"
        raise AssertionError(f"comando inatteso: {comando}")

    return esegui


def test_rilascio_indicato_vince_su_github_sha(
    prepara: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_SHA", VECCHIO)
    assert prepara.rilascio(SHA) == SHA


def test_rilascio_da_github_sha(prepara: types.ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setattr(prepara, "esegui", git_finto(" M file.py\n"))
    assert prepara.rilascio(None) == SHA


def test_rilascio_albero_modificato_e_sviluppo(
    prepara: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(prepara, "esegui", git_finto(" M scripts/prepara_app.py\n"))
    assert prepara.rilascio(None) == "sviluppo"


def test_rilascio_albero_pulito_e_head(
    prepara: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(prepara, "esegui", git_finto(""))
    assert prepara.rilascio(None) == SHA


@pytest.mark.parametrize("sha", ["0123abc", SHA.upper(), SHA + "0", "sviluppo"])
def test_rilascio_rifiuta_cio_che_non_e_uno_sha_completo(
    prepara: types.ModuleType, monkeypatch: pytest.MonkeyPatch, sha: str
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(prepara, "esegui", git_finto(""))
    with pytest.raises(SystemExit, match="rilascio non valido"):
        prepara.rilascio(sha)


# --- prepara_app.copia_analisi ----------------------------------------------------


def test_copia_analisi_porta_job_pipeline_e_pacchetto(
    prepara: types.ModuleType, tmp_path: Path
) -> None:
    sorgente = tmp_path / "src"
    (sorgente / "academy_analisi" / "__pycache__").mkdir(parents=True)
    (sorgente / "academy_analisi" / "tabelle.py").write_text("TABELLE = ()")
    (sorgente / "academy_analisi" / "__pycache__" / "tabelle.cpython-312.pyc").write_bytes(b"")
    (sorgente / "snapshot_bronze.py").write_text("")
    (sorgente / "pipeline_storico.py").write_text("")
    destinazione = tmp_path / "app"
    destinazione.mkdir()

    prepara.copia_analisi(sorgente, destinazione)

    copiati = sorted(p.relative_to(destinazione).as_posix() for p in destinazione.rglob("*"))
    assert copiati == [
        "analisi",
        "analisi/academy_analisi",
        "analisi/academy_analisi/tabelle.py",
        "analisi/pipeline_storico.py",
        "analisi/snapshot_bronze.py",
    ]


def test_copia_analisi_del_repository(prepara: types.ModuleType, tmp_path: Path) -> None:
    # I file che databricks.yml nomina (pipeline e task del job) devono esserci davvero.
    prepara.copia_analisi(prepara.ANALISI, tmp_path)
    bundle = (prepara.RADICE / "databricks.yml").read_text(encoding="utf-8")
    nominati = set(re.findall(r"\./build/app/(analisi/[\w/]+\.py)", bundle))

    assert len(nominati) >= 6
    for file in [*sorted(nominati), "analisi/academy_analisi/storico.py"]:
        assert (tmp_path / file).is_file(), file


# --- fumo_rilascio.attendi_health -------------------------------------------------


class Orologio:
    """Tempo finto: sleep fa avanzare monotonic, niente attese vere."""

    def __init__(self) -> None:
        self.adesso = 0.0
        self.pause: list[float] = []

    def monotonic(self) -> float:
        return self.adesso

    def sleep(self, secondi: float) -> None:
        self.pause.append(secondi)
        self.adesso += secondi


Esito = tuple[int, str, str] | BaseException


def health(rilascio: str, ambiente: str = "collaudo", stato: str = "ok") -> Esito:
    corpo = json.dumps({"stato": stato, "ambiente": ambiente, "rilascio": rilascio})
    return (200, "application/json", corpo)


@pytest.fixture
def orologio(fumo: types.ModuleType, monkeypatch: pytest.MonkeyPatch) -> Orologio:
    finto = Orologio()
    monkeypatch.setattr(fumo, "time", finto)
    return finto


def risposte(
    fumo: types.ModuleType, monkeypatch: pytest.MonkeyPatch, esiti: list[Esito]
) -> list[str]:
    """Sostituisce `apri`: un esito per chiamata, l'ultimo si ripete. Rende gli URL chiesti."""
    chiesti: list[str] = []
    sequenza: Iterator[Esito] = iter(esiti)
    ultimo: list[Esito] = [esiti[-1]]

    def apri(req: urllib.request.Request) -> tuple[int, str, str]:
        chiesti.append(req.full_url)
        esito = next(sequenza, ultimo[0])
        if isinstance(esito, BaseException):
            raise esito
        return esito

    monkeypatch.setattr(fumo, "apri", apri)
    return chiesti


def test_health_subito_giusta(
    fumo: types.ModuleType,
    orologio: Orologio,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chiesti = risposte(fumo, monkeypatch, [health(SHA)])
    fumo.attendi_health("https://app", "tok", "collaudo", SHA)
    assert chiesti == ["https://app/health"]
    assert orologio.pause == []
    assert f"ok  rilascio {SHA}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "guasto",
    [
        urllib.error.URLError("connessione rifiutata"),
        TimeoutError("lettura scaduta"),
        ConnectionResetError("chiusa dal proxy"),
        (200, "text/html", "<html>riavvio in corso</html>"),
        (502, "text/html", "Bad Gateway"),
    ],
    ids=["URLError", "TimeoutError", "ConnectionError", "non-JSON", "HTTP-502"],
)
def test_health_riprova_mentre_l_app_si_riavvia(
    fumo: types.ModuleType, orologio: Orologio, monkeypatch: pytest.MonkeyPatch, guasto: Esito
) -> None:
    chiesti = risposte(fumo, monkeypatch, [guasto, health(VECCHIO), health(SHA)])
    fumo.attendi_health("https://app", "tok", "collaudo", SHA)
    assert len(chiesti) == 3
    assert orologio.pause == [fumo.PAUSA, fumo.PAUSA]


def test_health_versione_vecchia_fino_alla_scadenza(
    fumo: types.ModuleType, orologio: Orologio, monkeypatch: pytest.MonkeyPatch
) -> None:
    risposte(fumo, monkeypatch, [health(VECCHIO)])
    with pytest.raises(SystemExit, match=f"ancora rilascio {VECCHIO}, non {SHA}"):
        fumo.attendi_health("https://app", "tok", "collaudo", SHA)
    assert orologio.adesso >= fumo.ATTESA_MASSIMA


def test_health_senza_risposta_fino_alla_scadenza(
    fumo: types.ModuleType, orologio: Orologio, monkeypatch: pytest.MonkeyPatch
) -> None:
    risposte(fumo, monkeypatch, [TimeoutError()])
    with pytest.raises(SystemExit, match=r"nessuna risposta \(TimeoutError\)"):
        fumo.attendi_health("https://app", "tok", "collaudo", SHA)
    assert orologio.adesso >= fumo.ATTESA_MASSIMA


def test_health_ambiente_sbagliato_fallisce_subito(
    fumo: types.ModuleType, orologio: Orologio, monkeypatch: pytest.MonkeyPatch
) -> None:
    risposte(fumo, monkeypatch, [health(SHA, ambiente="produzione")])
    with pytest.raises(SystemExit, match="FALLITO: ambiente collaudo"):
        fumo.attendi_health("https://app", "tok", "collaudo", SHA)
    assert orologio.pause == []


def test_health_stato_non_ok_fallisce_subito(
    fumo: types.ModuleType, orologio: Orologio, monkeypatch: pytest.MonkeyPatch
) -> None:
    risposte(fumo, monkeypatch, [health(SHA, stato="degradato")])
    with pytest.raises(SystemExit, match="FALLITO: /health risponde ok"):
        fumo.attendi_health("https://app", "tok", "collaudo", SHA)
