"""Test di fumo dell'App dopo un rilascio (ADR-0013), solo libreria standard.

    python scripts/fumo_rilascio.py --app academy-hub-collaudo --ambiente collaudo \
        --rilascio "$(cat build/app/RILASCIO)"

Credenziali del service principal dalle variabili DATABRICKS_HOST, DATABRICKS_CLIENT_ID e
DATABRICKS_CLIENT_SECRET (OAuth M2M): con queste chiede un token e passa dal proxy delle
App come qualunque utente. Controlla che:

- /health risponda `ok` con l'ambiente atteso e lo SHA dell'artifact appena rilasciato
  (riprova per qualche minuto: dopo il deploy l'App si riavvia);
- la configurazione pubblica dell'API e la pagina del frontend rispondano;
- senza token il proxy rifiuti la richiesta.

Niente scritture: in produzione ci sono dati veri dell'ambiente, anche se sintetici.
Esce con 1 al primo controllo fallito.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Il WAF di Databricks rifiuta lo User-Agent di difetto di urllib (403).
AGENTE = "academy-hub-fumo/1.0"
ATTESA_MASSIMA = 300  # secondi
PAUSA = 10


def richiesta(
    url: str, token: str | None = None, dati: bytes | None = None
) -> urllib.request.Request:
    intestazioni = {"User-Agent": AGENTE}
    if token is not None:
        intestazioni["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, data=dati, headers=intestazioni)  # noqa: S310 - https


class SenzaRedirect(urllib.request.HTTPRedirectHandler):
    """Senza token il proxy rimanda al login: il 302 è l'esito da controllare, non da seguire."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


APRI = urllib.request.build_opener(SenzaRedirect)


def apri(req: urllib.request.Request) -> tuple[int, str, str]:
    """Stato, Content-Type e corpo; gli errori HTTP diventano un esito, non un'eccezione."""
    try:
        with APRI.open(req, timeout=30) as risposta:
            return (
                risposta.status,
                risposta.headers.get("Content-Type", ""),
                risposta.read().decode(),
            )
    except urllib.error.HTTPError as errore:
        return (
            errore.code,
            errore.headers.get("Content-Type", ""),
            errore.read().decode(errors="replace"),
        )


def variabile(nome: str) -> str:
    valore = os.environ.get(nome)
    if not valore:
        sys.exit(f"manca la variabile {nome}")
    return valore


def token_m2m(host: str) -> str:
    dati = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": "all-apis"}
    ).encode()
    req = richiesta(f"{host}/oidc/v1/token", dati=dati)
    credenziali = f"{variabile('DATABRICKS_CLIENT_ID')}:{variabile('DATABRICKS_CLIENT_SECRET')}"
    req.add_unredirected_header(
        "Authorization", "Basic " + base64.b64encode(credenziali.encode()).decode()
    )
    stato, _, corpo = apri(req)
    if stato != 200:
        sys.exit(f"token OAuth M2M non ottenuto: HTTP {stato}")
    return json.loads(corpo)["access_token"]


def url_app(host: str, token: str, nome: str) -> str:
    stato, _, corpo = apri(richiesta(f"{host}/api/2.0/apps/{urllib.parse.quote(nome)}", token))
    if stato != 200:
        sys.exit(f"App {nome} non trovata: HTTP {stato}")
    app: dict[str, Any] = json.loads(corpo)
    url = app.get("url")
    if not url:
        sys.exit(f"App {nome} senza URL (stato {app.get('app_status')})")
    return url.rstrip("/")


def controlla(condizione: bool, messaggio: str) -> None:
    if not condizione:
        sys.exit(f"FALLITO: {messaggio}")
    print(f"ok  {messaggio}")


def attendi_health(base: str, token: str, ambiente: str, rilascio: str) -> None:
    """Dopo il deploy il proxy può rispondere ancora con la versione precedente."""
    scadenza = time.monotonic() + ATTESA_MASSIMA
    ultimo = "nessuna risposta"
    while time.monotonic() < scadenza:
        stato, _, corpo = apri(richiesta(f"{base}/health", token))
        if stato == 200:
            salute: dict[str, str] = json.loads(corpo)
            if salute.get("rilascio") == rilascio:
                controlla(salute.get("stato") == "ok", "/health risponde ok")
                controlla(salute.get("ambiente") == ambiente, f"ambiente {ambiente}")
                controlla(True, f"rilascio {rilascio}")
                return
            ultimo = f"rilascio {salute.get('rilascio')}"
        else:
            ultimo = f"HTTP {stato}"
        print(f"..  /health: {ultimo}, riprovo fra {PAUSA} s")
        time.sleep(PAUSA)
    sys.exit(f"FALLITO: dopo {ATTESA_MASSIMA} s /health dà ancora {ultimo}, non {rilascio}")


def main() -> int:
    argomenti = argparse.ArgumentParser(description="Test di fumo dell'App rilasciata")
    argomenti.add_argument("--app", required=True, help="nome dell'App, es. academy-hub-collaudo")
    argomenti.add_argument("--ambiente", required=True, choices=["collaudo", "produzione"])
    argomenti.add_argument("--rilascio", required=True, help="SHA atteso in /health")
    opzioni = argomenti.parse_args()

    host = variabile("DATABRICKS_HOST").rstrip("/")
    if not host.startswith("https://"):
        host = f"https://{host}"
    token = token_m2m(host)
    base = url_app(host, token, opzioni.app)

    attendi_health(base, token, opzioni.ambiente, opzioni.rilascio)

    stato, tipo, corpo = apri(richiesta(f"{base}/api/v1/configurazione", token))
    controlla(stato == 200 and tipo.startswith("application/json"), "configurazione dell'API")
    controlla(json.loads(corpo).get("identita") == "databricks", "identità dal proxy di Databricks")

    stato, tipo, corpo = apri(richiesta(f"{base}/", token))
    controlla(
        stato == 200 and tipo.startswith("text/html") and '<div id="root">' in corpo,
        "pagina del frontend",
    )

    stato, _, _ = apri(richiesta(f"{base}/health"))
    controlla(stato in (302, 401, 403), f"senza token il proxy rifiuta (HTTP {stato})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
