"""Contratto fra lo schema dell'App e la parte analitica (ADR-0016).

Il job `analisi` legge da Lakebase le colonne elencate in analisi/src/academy_analisi/
tabelle.py. Se una migrazione rinomina o toglie una di quelle colonne, lo snapshot
fallirebbe solo su Databricks: questo test lo dice prima, nella PR della migrazione.
tabelle.py è Python puro (niente pyspark) e si carica dal percorso, come gli script.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import pytest

from academy_hub.db.modelli import Base

TABELLE_ANALISI = (
    Path(__file__).resolve().parents[2] / "analisi" / "src" / "academy_analisi" / "tabelle.py"
)


def _carica() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tabelle_analisi", TABELLE_ANALISI)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    # Le dataclass cercano il modulo in sys.modules.
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class TabellaAnalisi(Protocol):
    nome: str
    colonne: tuple[str, ...]
    chiave: tuple[str, ...]


TABELLE = cast("tuple[TabellaAnalisi, ...]", _carica().TABELLE)


@pytest.mark.parametrize("tabella", TABELLE, ids=lambda t: t.nome)
def test_colonne_lette_esistono_nel_modello(tabella: TabellaAnalisi) -> None:
    modello = Base.metadata.tables[tabella.nome]

    assert set(tabella.colonne) <= {c.name for c in modello.columns}
    assert tabella.chiave == tuple(c.name for c in modello.primary_key.columns)
