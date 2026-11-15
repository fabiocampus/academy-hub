"""Metriche DORA dai deployment di GitHub (ADR-0015, docs/dora.md), solo libreria standard.

    python scripts/dora.py                          # markdown su stdout, environment prod
    python scripts/dora.py --giorni 30 --environment collaudo
    python scripts/dora.py --aggiorna docs/dora.md  # riscrive l'istantanea fra i marcatori

Ogni job con `environment:` registra un deployment nell'environment di GitHub, con i suoi
stati (waiting, queued, in_progress, success, failure, ...) e il link alla run. Da qui:

- frequenza dei rilasci: rilasci riusciti per settimana nel periodo;
- lead time for changes: dal commit su main (committer date: con lo squash merge è il
  merge della PR) al rilascio riuscito che lo porta nell'ambiente, mediana sui commit;
- change failure rate: rilasci falliti, o riusciti e poi annullati da un rollback, sul
  totale dei rilasci;
- tempo di ripristino: da un rilascio fallito (o riuscito e poi annullato) al primo
  deployment riuscito che lo segue, mediana.

I deployment di rollback.yml sono rollback: non contano come rilasci, ma ripristinano.
Token: GH_TOKEN o GITHUB_TOKEN, altrimenti `gh auth token`, altrimenti senza (60
richieste l'ora).
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

API = "https://api.github.com"
AGENTE = "academy-hub-dora/1.0"
REPO = "fabiocampus/academy-hub"
TERMINALI = ("success", "failure", "error")
INIZIO = "<!-- dora:inizio -->"
FINE = "<!-- dora:fine -->"

Json = Any
Leggi = Callable[[str], Json]


@dataclass(frozen=True)
class Deployment:
    """Un deployment arrivato a uno stato finale (success, failure o error)."""

    id: int
    sha: str
    rollback: bool
    riuscito: bool
    fine: datetime
    commit: tuple[datetime, ...] = ()
    """Committer date dei commit che il deployment porta per la prima volta (solo rilasci
    riusciti): quelli fra il rilascio riuscito precedente e questo."""


@dataclass(frozen=True)
class Metriche:
    da: datetime
    a: datetime
    rilasci: int
    riusciti: int
    rollback: int
    falliti: int
    lead_time: timedelta | None
    commit: int
    ripristino: timedelta | None
    ripristini: int

    @property
    def per_settimana(self) -> float:
        settimane = (self.a - self.da) / timedelta(weeks=1)
        return self.riusciti / settimane if settimane > 0 else 0.0

    @property
    def change_failure_rate(self) -> float | None:
        return self.falliti / self.rilasci if self.rilasci else None


# --- calcolo (puro) ---------------------------------------------------------------


def falliti(deployment: Sequence[Deployment]) -> list[Deployment]:
    """Rilasci falliti, o riusciti e annullati dal deployment successivo (un rollback)."""
    esito: list[Deployment] = []
    for i, d in enumerate(deployment):
        if d.rollback:
            continue
        dopo = deployment[i + 1] if i + 1 < len(deployment) else None
        if not d.riuscito or (dopo is not None and dopo.rollback):
            esito.append(d)
    return esito


def tempi_di_ripristino(deployment: Sequence[Deployment]) -> list[timedelta]:
    """Da ogni rilascio fallito al primo deployment riuscito che lo segue.

    Più rilasci falliti di fila hanno lo stesso ripristino: conta il primo guasto.
    """
    tempi: list[timedelta] = []
    guasto: datetime | None = None
    da_annullare = {d.id for d in falliti(deployment)}
    for d in deployment:
        if guasto is not None and d.riuscito and d.id not in da_annullare:
            tempi.append(d.fine - guasto)
            guasto = None
        if d.id in da_annullare and guasto is None:
            guasto = d.fine
    return tempi


def mediana(valori: Iterable[timedelta]) -> timedelta | None:
    secondi = [v.total_seconds() for v in valori]
    return timedelta(seconds=statistics.median(secondi)) if secondi else None


def metriche(deployment: Sequence[Deployment], da: datetime, a: datetime) -> Metriche:
    """Metriche dei deployment finiti in [da, a]; `deployment` in ordine di `fine`."""
    nel_periodo = [d for d in deployment if da <= d.fine <= a]
    rilasci = [d for d in nel_periodo if not d.rollback]
    lead = [d.fine - c for d in rilasci if d.riuscito for c in d.commit]
    ripristino = tempi_di_ripristino(nel_periodo)
    return Metriche(
        da=da,
        a=a,
        rilasci=len(rilasci),
        riusciti=sum(d.riuscito for d in rilasci),
        rollback=sum(d.rollback for d in nel_periodo),
        falliti=len(falliti(nel_periodo)),
        lead_time=mediana(lead),
        commit=len(lead),
        ripristino=mediana(ripristino),
        ripristini=len(ripristino),
    )


def durata(valore: timedelta | None) -> str:
    if valore is None:
        return "n/d"
    minuti = round(valore.total_seconds() / 60)
    if minuti < 60:
        return f"{minuti} min"
    ore, minuti = divmod(minuti, 60)
    if ore < 48:
        return f"{ore} h {minuti:02d} min"
    return f"{ore / 24:.1f} giorni"


def giorno(valore: datetime) -> str:
    return valore.strftime("%Y-%m-%d %H:%M UTC")


def markdown(m: Metriche, deployment: Sequence[Deployment], environment: str, repo: str) -> str:
    cfr = m.change_failure_rate
    righe = [
        f"Environment `{environment}` di `{repo}`, deployment finiti fra il "
        f"{giorno(m.da)} e il {giorno(m.a)}.",
        "",
        "| Metrica | Valore | Base |",
        "| --- | --- | --- |",
        f"| Frequenza dei rilasci | {m.per_settimana:.1f} a settimana "
        f"| {m.riusciti} rilasci riusciti |",
        f"| Lead time for changes (mediana) | {durata(m.lead_time)} | {m.commit} commit |",
        "| Change failure rate | "
        + ("n/d" if cfr is None else f"{cfr:.0%}")
        + f" | {m.falliti} falliti o annullati su {m.rilasci} rilasci |",
        f"| Tempo di ripristino (mediana) | {durata(m.ripristino)} "
        f"| {m.ripristini} ripristini, {m.rollback} rollback |",
        "",
        "| Fine | Tipo | Esito | Commit della run |",
        "| --- | --- | --- | --- |",
    ]
    annullati = {d.id for d in falliti(deployment)}
    for d in deployment:
        if not m.da <= d.fine <= m.a:
            continue
        tipo = "rollback" if d.rollback else "rilascio"
        esito = "riuscito" if d.riuscito else "fallito"
        if d.riuscito and d.id in annullati:
            esito = "riuscito, poi annullato"
        righe.append(f"| {giorno(d.fine)} | {tipo} | {esito} | `{d.sha[:7]}` |")
    return "\n".join(righe) + "\n"


def sostituisci_istantanea(testo: str, istantanea: str) -> str:
    inizio, fine = testo.find(INIZIO), testo.find(FINE)
    if inizio < 0 or fine < inizio:
        raise ValueError(f"marcatori {INIZIO} e {FINE} mancanti")
    return testo[: inizio + len(INIZIO)] + "\n" + istantanea + testo[fine:]


# --- lettura da GitHub ------------------------------------------------------------


def data(valore: str) -> datetime:
    return datetime.fromisoformat(valore.replace("Z", "+00:00"))


def esito_finale(stati: Sequence[Json]) -> Json | None:
    """Lo stato finale più recente (GitHub li dà dal più recente); `inactive` si ignora."""
    for stato in stati:
        if stato["state"] in TERMINALI:
            return stato
    return None


def run_del_log(url: str) -> int | None:
    trovato = re.search(r"/actions/runs/(\d+)", url or "")
    return int(trovato.group(1)) if trovato else None


def percorso_della_run(leggi: Leggi, base: str, run: int) -> str:
    """Percorso del workflow della run; "" se la run non c'è più (cancellata): rilascio."""
    try:
        return leggi(f"{base}/actions/runs/{run}")["path"]
    except urllib.error.HTTPError as errore:
        if errore.code != 404:
            raise
        print(f"avviso: run {run} non trovata, contata come rilascio", file=sys.stderr)
        return ""


def deployment_finiti(
    leggi: Leggi, elenco: Callable[[str], Iterator[Json]], repo: str, environment: str
) -> list[Deployment]:
    """Deployment dell'environment con stato finale, in ordine di fine, con i commit nuovi."""
    base = f"/repos/{repo}"
    grezzi: list[tuple[datetime, Json, Json]] = []
    for d in elenco(f"{base}/deployments?environment={environment}&per_page=100"):
        finale = esito_finale(list(elenco(f"{base}/deployments/{d['id']}/statuses?per_page=100")))
        if finale is not None:
            grezzi.append((data(finale["created_at"]), d, finale))
    grezzi.sort(key=lambda t: t[0])

    percorsi: dict[int, str] = {}
    risultato: list[Deployment] = []
    precedente: str | None = None  # SHA dell'ultimo rilascio riuscito
    for fine, d, finale in grezzi:
        run = run_del_log(finale.get("log_url") or finale.get("target_url") or "")
        if run is not None and run not in percorsi:
            percorsi[run] = percorso_della_run(leggi, base, run)
        rollback = run is not None and percorsi[run].endswith("/rollback.yml")
        riuscito = finale["state"] == "success"
        commit: tuple[datetime, ...] = ()
        if riuscito and not rollback:
            if precedente is None:
                commit = (data(leggi(f"{base}/commits/{d['sha']}")["commit"]["committer"]["date"]),)
                precedente = d["sha"]
            elif precedente != d["sha"]:
                # Fino a 250 commit (compare non pagina oltre): basta fra due rilasci.
                confronto = leggi(f"{base}/compare/{precedente}...{d['sha']}")
                # Uno SHA più vecchio dell'ultimo rilasciato (prod approvati in ordine
                # inverso) non porta commit nuovi e non sposta il riferimento: altrimenti
                # i commit del rilascio dopo conterebbero due volte.
                if confronto["status"] == "ahead":
                    commit = tuple(
                        data(c["commit"]["committer"]["date"]) for c in confronto["commits"]
                    )
                    precedente = d["sha"]
        risultato.append(Deployment(d["id"], d["sha"], rollback, riuscito, fine, commit))
    return risultato


def token() -> str | None:
    for nome in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(nome):
            return os.environ[nome]
    gh = shutil.which("gh") or shutil.which("C:/Program Files/GitHub CLI/gh.exe")
    if gh is None:
        return None
    esito = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, check=False)  # noqa: S603
    return esito.stdout.strip() or None


class ClientGitHub:
    def __init__(self, credenziale: str | None) -> None:
        self.intestazioni = {
            "Accept": "application/vnd.github+json",
            "User-Agent": AGENTE,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if credenziale:
            self.intestazioni["Authorization"] = f"Bearer {credenziale}"

    def _apri(self, url: str) -> tuple[Json, str]:
        if url.startswith("/"):
            url = API + url
        for tentativo in range(4):
            req = urllib.request.Request(url, headers=self.intestazioni)  # noqa: S310 - https
            try:
                with urllib.request.urlopen(req, timeout=30) as risposta:  # noqa: S310
                    return json.load(risposta), risposta.headers.get("Link", "")
            except urllib.error.HTTPError:
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if tentativo == 3:
                    raise
                time.sleep(2**tentativo)
        raise AssertionError("irraggiungibile")

    def leggi(self, url: str) -> Json:
        return self._apri(url)[0]

    def elenco(self, url: str) -> Iterator[Json]:
        prossimo: str | None = url
        while prossimo:
            pagina, link = self._apri(prossimo)
            yield from pagina
            trovato = re.search(r'<([^>]+)>;\s*rel="next"', link)
            prossimo = trovato.group(1) if trovato else None


def main() -> int:
    argomenti = argparse.ArgumentParser(description="Metriche DORA dai deployment di GitHub")
    argomenti.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", REPO))
    argomenti.add_argument("--environment", default="prod")
    argomenti.add_argument("--giorni", type=int, default=90, help="periodo, fino a ora")
    argomenti.add_argument("--aggiorna", metavar="FILE", help="riscrive l'istantanea nel file")
    opzioni = argomenti.parse_args()

    client = ClientGitHub(token())
    deployment = deployment_finiti(client.leggi, client.elenco, opzioni.repo, opzioni.environment)
    # timezone.utc e non datetime.UTC: lo script gira anche col Python di sistema (3.10).
    a = datetime.now(timezone.utc)  # noqa: UP017 - non troncare: escluderebbe il deployment appena finito
    m = metriche(deployment, a - timedelta(days=opzioni.giorni), a)
    testo = markdown(m, deployment, opzioni.environment, opzioni.repo)
    if opzioni.aggiorna:
        with open(opzioni.aggiorna, encoding="utf-8") as f:
            vecchio = f.read()
        with open(opzioni.aggiorna, "w", encoding="utf-8", newline="\n") as f:
            f.write(sostituisci_istantanea(vecchio, testo))
    else:
        sys.stdout.write(testo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
