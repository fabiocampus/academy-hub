"""Prepara in `build/app/` il codice della Databricks App (ADR-0010), solo libreria standard.

    python scripts/prepara_app.py            # compila anche il frontend (npm ci + build)
    python scripts/prepara_app.py --senza-npm   # riusa frontend/dist già compilato
    databricks bundle deploy -t collaudo ...  # poi il bundle carica build/app

Databricks Apps installa `requirements.txt` con pip ed esegue il comando dichiarato nel
bundle dalla cartella dell'App. Dentro finiscono:

    academy_hub/       il pacchetto Python (backend/src/academy_hub)
    frontend/          la build statica (frontend/dist), servita da FastAPI
    requirements.txt   dipendenze di runtime fissate con gli hash, da uv.lock

`build/` è ignorata da Git: si rigenera a ogni deploy, la sorgente resta il repository.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
BACKEND = RADICE / "backend"
FRONTEND = RADICE / "frontend"
DESTINAZIONE = RADICE / "build" / "app"


def esegui(comando: list[str], cartella: Path) -> str:
    # shell=False; su Windows npm è npm.cmd: lo trova shutil.which.
    eseguibile = shutil.which(comando[0])
    if eseguibile is None:
        sys.exit(f"{comando[0]} non trovato nel PATH")
    risultato = subprocess.run(  # noqa: S603 - comandi fissi, nessun input esterno
        [eseguibile, *comando[1:]], cwd=cartella, capture_output=True, text=True, check=False
    )
    if risultato.returncode != 0:
        sys.stderr.write(risultato.stdout + risultato.stderr)
        sys.exit(f"{' '.join(comando)} fallito (codice {risultato.returncode})")
    return risultato.stdout


def main() -> int:
    argomenti = argparse.ArgumentParser(description="Prepara build/app per la Databricks App")
    argomenti.add_argument("--senza-npm", action="store_true", help="non ricompilare il frontend")
    opzioni = argomenti.parse_args()

    if not opzioni.senza_npm:
        esegui(["npm", "ci"], FRONTEND)
        esegui(["npm", "run", "build"], FRONTEND)
    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("frontend/dist/index.html mancante: lancia senza --senza-npm")

    if DESTINAZIONE.exists():
        shutil.rmtree(DESTINAZIONE)
    DESTINAZIONE.mkdir(parents=True)
    shutil.copytree(
        BACKEND / "src" / "academy_hub",
        DESTINAZIONE / "academy_hub",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(dist, DESTINAZIONE / "frontend")
    esporta = ["uv", "export", "--frozen", "--no-dev", "--no-emit-project"]
    requisiti = esegui([*esporta, "--format", "requirements.txt"], BACKEND)
    (DESTINAZIONE / "requirements.txt").write_text(requisiti, encoding="utf-8", newline="\n")
    print(f"App pronta in {DESTINAZIONE.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
