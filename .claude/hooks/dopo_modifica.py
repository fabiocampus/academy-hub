"""Hook PostToolUse: dopo una modifica a un file Python del backend lancia ruff e i test.

Legge l'evento JSON da stdin. Se qualcosa fallisce esce con codice 2 e scrive
l'errore su stderr, così Claude Code lo mostra all'agente.
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def esegui(comando: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        comando, cwd=BACKEND, capture_output=True, text=True, check=False
    )


def main() -> int:
    evento = json.load(sys.stdin)
    percorso = evento.get("tool_input", {}).get("file_path", "")
    if not percorso:
        return 0
    file = Path(percorso).resolve()
    if file.suffix != ".py" or BACKEND not in file.parents:
        return 0

    passi = [
        ["uv", "run", "ruff", "format", str(file)],
        ["uv", "run", "ruff", "check", "--fix", str(file)],
        ["uv", "run", "pytest", "-q", "-x", "--no-header"],
    ]
    for passo in passi:
        esito = esegui(passo)
        if esito.returncode != 0:
            print(f"{' '.join(passo[2:])} fallito:\n{esito.stdout}{esito.stderr}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
