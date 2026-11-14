"""Test di contratto: l'API pubblicata coincide con `backend/contratto/openapi.json`."""

import json

from academy_hub.api import PREFISSO, VERSIONE_API
from academy_hub.contratto import CONTRATTO, genera, impronta, leggi_impronte, serializza

RIGENERA = "uv run python -m academy_hub.contratto"


def test_l_api_coincide_con_il_contratto_nel_repository() -> None:
    assert serializza(genera()) == CONTRATTO.read_text(encoding="utf-8"), (
        f"L'API non coincide con il contratto nel repository: lancia `{RIGENERA}`."
    )


def test_il_contratto_non_cambia_senza_aumentare_la_versione() -> None:
    pubblicata = leggi_impronte().get(VERSIONE_API)

    assert pubblicata == impronta(genera()), (
        f"Il contratto {VERSIONE_API} è cambiato: aumenta VERSIONE_API, poi `{RIGENERA}`."
    )


def test_il_prefisso_segue_la_versione_maggiore() -> None:
    contratto = json.loads(CONTRATTO.read_text(encoding="utf-8"))

    assert contratto["info"]["version"] == VERSIONE_API
    assert f"/api/v{VERSIONE_API.split('.')[0]}" == PREFISSO
    assert all(p.startswith(PREFISSO) or p == "/health" for p in contratto["paths"])


def test_ogni_errore_documentato_e_problem_json() -> None:
    contratto = genera()

    for percorso, operazioni in contratto["paths"].items():
        for metodo, operazione in operazioni.items():
            for stato, risposta in operazione["responses"].items():
                if stato.startswith(("4", "5")):
                    assert "application/problem+json" in risposta["content"], (
                        f"{metodo.upper()} {percorso} {stato}"
                    )
