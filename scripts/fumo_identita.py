"""Prova di fumo dell'identità su docker compose (US-16, ADR-0008), solo libreria standard.

Prende token veri da Keycloak (client academy-cli, password grant) per gli utenti di
prova e percorre il flusso richiesta -> approvazione -> conferma, più i casi vietati.

    docker compose up -d --build --wait
    python scripts/fumo_identita.py

Usa la prima edizione del catalogo senza iscrizione del dipendente: dopo qualche giro
riparti da zero con `docker compose down -v`. Esce con 1 al primo controllo fallito.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

KEYCLOAK = os.environ.get("KEYCLOAK_URL", "http://127.0.0.1:8080")
API = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000") + "/api/v1"


def token(utente: str) -> str:
    # Utenti di prova del realm di sviluppo: la password è il nome utente.
    dati = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "academy-cli",
            "username": utente,
            "password": utente,
        }
    ).encode()
    url = f"{KEYCLOAK}/realms/academy/protocol/openid-connect/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=dati), timeout=10) as risposta:  # noqa: S310
        return json.load(risposta)["access_token"]


def chiama(
    metodo: str, percorso: str, utente: str | None, corpo: dict[str, Any] | None = None
) -> tuple[int, Any]:
    intestazioni = {"Content-Type": "application/json"}
    if utente is not None:
        intestazioni["Authorization"] = f"Bearer {token(utente)}"
    richiesta = urllib.request.Request(  # noqa: S310 (URL http dalle variabili)
        API + percorso,
        method=metodo,
        headers=intestazioni,
        data=None if corpo is None else json.dumps(corpo).encode(),
    )
    try:
        with urllib.request.urlopen(richiesta, timeout=10) as risposta:  # noqa: S310
            return risposta.status, json.load(risposta)
    except urllib.error.HTTPError as errore:
        return errore.code, json.load(errore)


def atteso(descrizione: str, stato: int, ottenuto: tuple[int, Any]) -> Any:
    codice, corpo = ottenuto
    esito = "ok " if codice == stato else "KO "
    print(f"{esito} {descrizione}: {codice} (atteso {stato})")
    if codice != stato:
        print(json.dumps(corpo, indent=2, ensure_ascii=False))
        sys.exit(1)
    return corpo


def main() -> None:
    atteso("catalogo senza token", 401, chiama("GET", "/catalogo", None))
    atteso("persona non registrata", 403, chiama("GET", "/catalogo", "esterna"))
    catalogo = atteso("catalogo del dipendente", 200, chiama("GET", "/catalogo", "dipendente"))
    libere = [e for e in catalogo["elementi"] if e["mia_iscrizione"] is None]
    if not libere:
        sys.exit("Nessuna edizione libera per il dipendente: docker compose down -v e riprova")
    edizione = libere[0]["edizione_id"]

    iscrizione = atteso(
        "richiesta del dipendente",
        201,
        chiama("POST", "/iscrizioni", "dipendente", {"edizione_id": edizione}),
    )["id"]
    approva = f"/iscrizioni/{iscrizione}/approvazione"
    atteso("il dipendente non approva", 403, chiama("POST", approva, "dipendente"))
    atteso("il docente non approva", 403, chiama("POST", approva, "docente"))
    atteso("la responsabile diretta approva", 200, chiama("POST", approva, "responsabile"))
    conferma = f"/iscrizioni/{iscrizione}/conferma"
    atteso("la responsabile non conferma", 403, chiama("POST", conferma, "responsabile"))
    confermata = atteso("l'admin conferma", 200, chiama("POST", conferma, "admin"))
    if confermata["stato"] != "Confermata":
        sys.exit(f"Stato atteso Confermata, ottenuto {confermata['stato']}")
    print("Flusso con token Keycloak completo.")


if __name__ == "__main__":
    main()
