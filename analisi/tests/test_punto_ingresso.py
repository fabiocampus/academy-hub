"""Punti d'ingresso dei task del job (spark_python_task su serverless)."""

import runpy
from pathlib import Path
from types import ModuleType

import pytest

from academy_analisi import gate, gold, snapshot

SORGENTI = Path(__file__).parents[1] / "src"

PUNTI = [
    ("snapshot_bronze.py", snapshot, "main"),
    ("controlli_qualita.py", gate, "main_controlli"),
    ("aggiorna_gold.py", gold, "main"),
    ("registra_esito.py", gate, "main_esito"),
]


@pytest.mark.parametrize(("script", "modulo", "funzione"), PUNTI)
def test_riuscito_non_solleva_system_exit(
    monkeypatch: pytest.MonkeyPatch, script: str, modulo: ModuleType, funzione: str
) -> None:
    # Su serverless lo script gira in IPython: anche SystemExit(0) fa fallire il task.
    monkeypatch.setattr(modulo, funzione, lambda: 0)

    runpy.run_path(str(SORGENTI / script), run_name="__main__")


@pytest.mark.parametrize(("script", "modulo", "funzione"), PUNTI)
def test_fallito_esce_con_il_suo_codice(
    monkeypatch: pytest.MonkeyPatch, script: str, modulo: ModuleType, funzione: str
) -> None:
    monkeypatch.setattr(modulo, funzione, lambda: 2)

    with pytest.raises(SystemExit) as uscita:
        runpy.run_path(str(SORGENTI / script), run_name="__main__")

    assert uscita.value.code == 2
