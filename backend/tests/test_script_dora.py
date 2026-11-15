"""Metriche DORA (`scripts/dora.py`, ADR-0015): calcolo puro e lettura dei deployment.

Lo script sta in `scripts/` (solo libreria standard): si carica dal file con importlib.
GitHub è sostituito da un dizionario url -> risposta.
"""

import importlib.util
import types
import urllib.error
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def dora() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("script_dora", SCRIPTS / "dora.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def ore(n: float) -> datetime:
    return T0 + timedelta(hours=n)


def dep(
    dora: types.ModuleType,
    id: int,
    fine: datetime,
    *,
    riuscito: bool = True,
    rollback: bool = False,
    commit: tuple[datetime, ...] = (),
) -> Any:
    return dora.Deployment(id, f"{id:040x}", rollback, riuscito, fine, commit)


# --- calcolo ----------------------------------------------------------------------


def test_senza_deployment_le_metriche_sono_vuote(dora: types.ModuleType) -> None:
    m = dora.metriche([], T0, ore(24 * 7))
    assert (m.rilasci, m.riusciti, m.falliti, m.rollback) == (0, 0, 0, 0)
    assert m.lead_time is None and m.ripristino is None
    assert m.change_failure_rate is None
    assert m.per_settimana == 0


def test_frequenza_conta_i_rilasci_riusciti_per_settimana(dora: types.ModuleType) -> None:
    deployment = [
        dep(dora, 1, ore(1)),
        dep(dora, 2, ore(2), riuscito=False),
        dep(dora, 3, ore(3)),
        dep(dora, 4, ore(4)),
    ]
    m = dora.metriche(deployment, T0, ore(24 * 14))
    assert m.riusciti == 3
    assert m.per_settimana == pytest.approx(1.5)


def test_lead_time_e_la_mediana_sui_commit_dei_rilasci_riusciti(
    dora: types.ModuleType,
) -> None:
    deployment = [
        dep(dora, 1, ore(10), commit=(ore(9), ore(4))),  # 1 h, 6 h
        dep(dora, 2, ore(20), riuscito=False, commit=(ore(0),)),  # non arrivato: escluso
        dep(dora, 3, ore(30), commit=(ore(28),)),  # 2 h
    ]
    m = dora.metriche(deployment, T0, ore(48))
    assert m.commit == 3
    assert m.lead_time == timedelta(hours=2)


def test_rilascio_fallito_conta_e_si_ripristina_col_successivo_riuscito(
    dora: types.ModuleType,
) -> None:
    deployment = [
        dep(dora, 1, ore(1)),
        dep(dora, 2, ore(2), riuscito=False),
        dep(dora, 3, ore(2.5), riuscito=False),  # stesso guasto: un solo ripristino
        dep(dora, 4, ore(3)),
    ]
    m = dora.metriche(deployment, T0, ore(24))
    assert (m.falliti, m.rilasci) == (2, 4)
    assert m.change_failure_rate == pytest.approx(0.5)
    assert (m.ripristini, m.ripristino) == (1, timedelta(hours=1))


def test_rilascio_annullato_da_un_rollback_e_un_fallimento(dora: types.ModuleType) -> None:
    deployment = [
        dep(dora, 1, ore(1)),
        dep(dora, 2, ore(2)),
        dep(dora, 3, ore(2.25), rollback=True),
        dep(dora, 4, ore(5), rollback=True),  # avanti di nuovo: non è un rilascio
    ]
    m = dora.metriche(deployment, T0, ore(24))
    assert (m.rilasci, m.riusciti, m.rollback, m.falliti) == (2, 2, 2, 1)
    assert m.ripristino == timedelta(minutes=15)
    assert [d.id for d in dora.falliti(deployment)] == [2]


def test_rollback_fallito_non_ripristina(dora: types.ModuleType) -> None:
    deployment = [
        dep(dora, 1, ore(1)),
        dep(dora, 2, ore(2), rollback=True, riuscito=False),
        dep(dora, 3, ore(3), rollback=True),
    ]
    m = dora.metriche(deployment, T0, ore(24))
    assert m.falliti == 1
    assert m.ripristino == timedelta(hours=2)


def test_metriche_solo_nel_periodo(dora: types.ModuleType) -> None:
    deployment = [dep(dora, 1, ore(-48), riuscito=False), dep(dora, 2, ore(1))]
    m = dora.metriche(deployment, T0, ore(24))
    assert (m.rilasci, m.falliti) == (1, 0)


@pytest.mark.parametrize(
    ("valore", "testo"),
    [
        (None, "n/d"),
        (timedelta(minutes=7, seconds=20), "7 min"),
        (timedelta(hours=2, minutes=5), "2 h 05 min"),
        (timedelta(days=3), "3.0 giorni"),
    ],
)
def test_durata(dora: types.ModuleType, valore: timedelta | None, testo: str) -> None:
    assert dora.durata(valore) == testo


def test_markdown_segna_il_rilascio_annullato(dora: types.ModuleType) -> None:
    deployment = [dep(dora, 1, ore(1)), dep(dora, 2, ore(2), rollback=True)]
    testo = dora.markdown(dora.metriche(deployment, T0, ore(24)), deployment, "prod", "o/r")
    assert "| Change failure rate | 100% |" in testo
    assert "| rilascio | riuscito, poi annullato |" in testo
    assert "| rollback | riuscito |" in testo


def test_istantanea_sostituita_fra_i_marcatori(dora: types.ModuleType) -> None:
    testo = f"prima\n{dora.INIZIO}\nvecchia\n{dora.FINE}\ndopo\n"
    assert (
        dora.sostituisci_istantanea(testo, "nuova\n")
        == f"prima\n{dora.INIZIO}\nnuova\n{dora.FINE}\ndopo\n"
    )
    with pytest.raises(ValueError, match="marcatori"):
        dora.sostituisci_istantanea("niente", "nuova\n")


# --- lettura da GitHub ------------------------------------------------------------

R = "/repos/o/r"
A, B, C = "a" * 40, "b" * 40, "c" * 40


def stato(state: str, quando: datetime, run: int) -> dict[str, Any]:
    return {
        "state": state,
        "created_at": quando.isoformat().replace("+00:00", "Z"),
        "log_url": f"https://github.com/o/r/actions/runs/{run}/job/1",
    }


def commit(quando: datetime) -> dict[str, Any]:
    return {"commit": {"committer": {"date": quando.isoformat().replace("+00:00", "Z")}}}


def test_deployment_finiti_da_github(dora: types.ModuleType) -> None:
    risposte: dict[str, Any] = {
        f"{R}/deployments?environment=prod&per_page=100": [
            # GitHub li dà dal più recente
            {"id": 5, "sha": B},  # in attesa di approvazione: escluso
            {"id": 4, "sha": B},  # rollback
            {"id": 3, "sha": B},
            {"id": 2, "sha": A},
            {"id": 1, "sha": C},  # fallito
        ],
        f"{R}/deployments/5/statuses?per_page=100": [stato("waiting", ore(9), 30)],
        f"{R}/deployments/4/statuses?per_page=100": [
            stato("success", ore(8), 40),
            stato("in_progress", ore(7.9), 40),
        ],
        f"{R}/deployments/3/statuses?per_page=100": [
            stato("inactive", ore(8), 30),
            stato("success", ore(6), 30),
            stato("waiting", ore(5), 30),
        ],
        f"{R}/deployments/2/statuses?per_page=100": [stato("success", ore(3), 20)],
        f"{R}/deployments/1/statuses?per_page=100": [stato("failure", ore(1), 10)],
        f"{R}/actions/runs/10": {"path": ".github/workflows/rilascio.yml"},
        f"{R}/actions/runs/20": {"path": ".github/workflows/rilascio.yml"},
        f"{R}/actions/runs/30": {"path": ".github/workflows/rilascio.yml"},
        f"{R}/actions/runs/40": {"path": ".github/workflows/rollback.yml"},
        f"{R}/commits/{A}": commit(ore(2)),
        f"{R}/compare/{A}...{B}": {
            "status": "ahead",
            "commits": [commit(ore(4)), commit(ore(5))],
        },
    }

    def leggi(url: str) -> Any:
        return risposte[url]

    def elenco(url: str) -> Iterator[Any]:
        yield from risposte[url]

    deployment = dora.deployment_finiti(leggi, elenco, "o/r", "prod")

    assert [(d.id, d.riuscito, d.rollback) for d in deployment] == [
        (1, False, False),
        (2, True, False),
        (3, True, False),
        (4, True, True),
    ]
    assert [d.fine for d in deployment] == [ore(1), ore(3), ore(6), ore(8)]
    assert deployment[0].commit == ()
    assert deployment[1].commit == (ore(2),)
    assert deployment[2].commit == (ore(4), ore(5))
    assert deployment[3].commit == ()


def test_rilascio_di_uno_sha_vecchio_non_sposta_il_riferimento(dora: types.ModuleType) -> None:
    """Prod approvati in ordine inverso: B (nuovo) prima di A (vecchio), poi C."""
    risposte: dict[str, Any] = {
        f"{R}/deployments?environment=prod&per_page=100": [
            {"id": 3, "sha": C},
            {"id": 2, "sha": A},
            {"id": 1, "sha": B},
        ],
        f"{R}/deployments/1/statuses?per_page=100": [stato("success", ore(1), 10)],
        f"{R}/deployments/2/statuses?per_page=100": [stato("success", ore(2), 20)],
        f"{R}/deployments/3/statuses?per_page=100": [stato("success", ore(3), 30)],
        f"{R}/commits/{B}": commit(ore(0)),
        f"{R}/compare/{B}...{A}": {"status": "behind", "commits": []},
        f"{R}/compare/{B}...{C}": {"status": "ahead", "commits": [commit(ore(2.5))]},
    }

    def leggi(url: str) -> Any:
        if "/actions/runs/" in url:
            # run cancellata: si conta come rilascio
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return risposte[url]

    def elenco(url: str) -> Iterator[Any]:
        yield from risposte[url]

    deployment = dora.deployment_finiti(leggi, elenco, "o/r", "prod")

    assert [d.rollback for d in deployment] == [False, False, False]
    assert [d.commit for d in deployment] == [(ore(0),), (), (ore(2.5),)]
