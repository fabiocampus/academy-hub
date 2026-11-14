"""Contratto OpenAPI versionato in `backend/contratto/`.

- `openapi.json`: il contratto generato dall'app, così com'è nel repository.
- `impronte.json`: per ogni `VERSIONE_API`, l'impronta SHA-256 del contratto senza
  `info.version`. Una versione pubblicata non cambia più impronta: se il contratto
  cambia, la versione va aumentata (semver: major se il cambio rompe i client).

`uv run python -m academy_hub.contratto` rigenera i due file; rifiuta di farlo se il
contratto è cambiato e la versione no.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from academy_hub.api import VERSIONE_API
from academy_hub.main import crea_app

CARTELLA = Path(__file__).resolve().parents[2] / "contratto"
CONTRATTO = CARTELLA / "openapi.json"
IMPRONTE = CARTELLA / "impronte.json"


def genera() -> dict[str, Any]:
    return crea_app().openapi()


def serializza(dati: dict[str, Any]) -> str:
    return json.dumps(dati, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def impronta(contratto: dict[str, Any]) -> str:
    senza_versione = copy.deepcopy(contratto)
    senza_versione["info"].pop("version", None)
    return hashlib.sha256(serializza(senza_versione).encode()).hexdigest()


def leggi_impronte() -> dict[str, str]:
    if not IMPRONTE.exists():
        return {}
    return json.loads(IMPRONTE.read_text(encoding="utf-8"))


def aggiorna() -> None:
    contratto = genera()
    nuova = impronta(contratto)
    impronte = leggi_impronte()
    pubblicata = impronte.get(VERSIONE_API)
    if pubblicata is not None and pubblicata != nuova:
        sys.exit(
            f"Il contratto è cambiato ma VERSIONE_API è ancora {VERSIONE_API}: "
            "aumentala in academy_hub/api/__init__.py e rilancia."
        )
    impronte[VERSIONE_API] = nuova
    CARTELLA.mkdir(exist_ok=True)
    CONTRATTO.write_bytes(serializza(contratto).encode())
    IMPRONTE.write_bytes(serializza(impronte).encode())
    print(f"Contratto {VERSIONE_API} scritto in {CONTRATTO}")


if __name__ == "__main__":
    aggiorna()
