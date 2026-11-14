"""Job di sistema (ADR-0007): scadenza all'inizio dell'edizione (US-17) e rete di sicurezza
della promozione dalla lista d'attesa (US-09). Autore degli eventi: il sistema.

```bash
python -m academy_hub.job             # una passata, poi termina
python -m academy_hub.job --ogni 300  # una passata ogni 300 secondi, finché non lo fermi
```

Legge `ACADEMY_DATABASE_URL` come il backend. Ogni edizione è una transazione a sé: un
errore su una non annulla il lavoro già fatto sulle altre, e i lock restano brevi.
"""

import argparse
import logging
import signal
import sys
import time
from dataclasses import dataclass
from types import FrameType

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from academy_hub.config import impostazioni
from academy_hub.servizi import iscrizioni

log = logging.getLogger("academy_hub.job")


@dataclass(frozen=True)
class Esito:
    annullate: int = 0
    promosse: int = 0


def esegui(motore: Engine) -> Esito:
    """Una passata: prima chiude le edizioni iniziate, poi ripara la promozione.

    Idempotente: lavora solo su iscrizioni ancora pendenti o su posti ancora liberi,
    quindi una seconda passata non trova nulla e non scrive audit.
    """
    annullate = promosse = 0
    with Session(motore) as sessione:
        with sessione.begin():
            da_chiudere = iscrizioni.edizioni_da_chiudere(sessione)
        for edizione_id in da_chiudere:
            with sessione.begin():
                annullate += iscrizioni.chiudi_edizione_iniziata(sessione, edizione_id)
        with sessione.begin():
            da_promuovere = iscrizioni.edizioni_da_promuovere(sessione)
        for edizione_id in da_promuovere:
            with sessione.begin():
                promosse += iscrizioni.promuovi_edizione(sessione, edizione_id)
    return Esito(annullate, promosse)


def _secondi(valore: str) -> int:
    secondi = int(valore)
    if secondi <= 0:
        raise argparse.ArgumentTypeError("deve essere un numero di secondi maggiore di zero")
    return secondi


def _ferma(_segnale: int, _frame: FrameType | None) -> None:
    # Nel container il processo è il PID 1: senza un gestore ignorerebbe SIGTERM.
    raise KeyboardInterrupt


def _passata(motore: Engine) -> None:
    esito = esegui(motore)
    log.info("Passata del job: %d annullate, %d promosse", esito.annullate, esito.promosse)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m academy_hub.job",
        description="Job di sistema: scadenza delle iscrizioni e promozione dalla lista d'attesa",
    )
    parser.add_argument(
        "--ogni", type=_secondi, metavar="SECONDI", help="ripete la passata ogni SECONDI"
    )
    ogni: int | None = parser.parse_args(argv).ogni
    config = impostazioni()
    logging.basicConfig(level=config.livello_log, format="%(asctime)s %(levelname)s %(message)s")
    motore = create_engine(config.database_url, pool_pre_ping=True)
    try:
        if ogni is None:
            _passata(motore)
            return 0
        signal.signal(signal.SIGTERM, _ferma)
        while True:
            try:
                _passata(motore)
            except Exception:
                log.exception("Passata del job fallita: riprovo al prossimo giro")
            time.sleep(ogni)
    except KeyboardInterrupt:
        log.info("Job fermato")
        return 0
    finally:
        motore.dispose()


if __name__ == "__main__":
    sys.exit(main())
