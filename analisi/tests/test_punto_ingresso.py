"""Punto d'ingresso del task `snapshot` (spark_python_task su serverless)."""

import runpy
from pathlib import Path

import pytest

from academy_analisi import snapshot

SCRIPT = Path(__file__).parents[1] / "src" / "snapshot_bronze.py"


def test_riuscito_non_solleva_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Su serverless lo script gira in IPython: anche SystemExit(0) fa fallire il task.
    monkeypatch.setattr(snapshot, "main", lambda: 0)

    runpy.run_path(str(SCRIPT), run_name="__main__")


def test_fallito_esce_con_il_suo_codice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot, "main", lambda: 2)

    with pytest.raises(SystemExit) as uscita:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert uscita.value.code == 2
