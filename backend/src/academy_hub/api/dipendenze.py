"""Dipendenze condivise dalle rotte: transazione per richiesta, identità, versione attesa."""

import re
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from academy_hub.api.errori import EtagNonValido, PrecondizioneRichiesta
from academy_hub.config import impostazioni
from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import NonAutenticato
from academy_hub.repository import persone


def _sessione(richiesta: Request) -> Iterator[Session]:
    """Unità di lavoro: una transazione per richiesta.

    Commit se la rotta termina senza errori, rollback altrimenti. Con `scope="function"`
    il commit avviene prima di inviare la risposta: un errore del commit diventa la
    risposta, invece di un 200 per un dato mai salvato.
    """
    motore: Engine = richiesta.app.state.motore
    with Session(motore, expire_on_commit=False) as sessione, sessione.begin():
        yield sessione


SessioneDb = Annotated[Session, Depends(_sessione, scope="function")]


_PERSONA_ID = re.compile(r"^[1-9]\d{0,18}$")


def _attore(
    sessione: SessioneDb,
    x_persona_id: Annotated[
        str | None,
        Header(
            description="Identità provvisoria della fase 5 (id numerico della persona), "
            "accettata solo in locale con ACADEMY_IDENTITA_PROVVISORIA=true. "
            "Dalla fase 6 l'identità arriva dal token OIDC."
        ),
    ] = None,
) -> Attore:
    if x_persona_id is None or not impostazioni().identita_provvisoria:
        raise NonAutenticato("Identità mancante")
    if not _PERSONA_ID.match(x_persona_id):
        raise NonAutenticato("Identità non valida")
    attore = persone.attore(sessione, int(x_persona_id))
    if attore is None:
        raise NonAutenticato("Persona sconosciuta")
    return attore


AttoreCorrente = Annotated[Attore, Depends(_attore)]


_ETAG = re.compile(r'^"(\d+)"$')


def etag(versione: int) -> str:
    return f'"{versione}"'


def _versione_attesa(
    if_match: Annotated[
        str | None, Header(description="ETag letto con la GET: concorrenza ottimistica")
    ] = None,
) -> int:
    if if_match is None:
        raise PrecondizioneRichiesta("Rileggi la risorsa e manda il suo ETag in If-Match")
    if if_match.strip() == "*":
        # RFC 9110 lo accetterebbe per qualunque versione: aggirerebbe la concorrenza ottimistica.
        raise PrecondizioneRichiesta("If-Match: * non è ammesso: manda l'ETag letto con la GET")
    trovato = _ETAG.match(if_match.strip())
    if trovato is None:
        raise EtagNonValido(if_match)
    return int(trovato.group(1))


VersioneAttesa = Annotated[int, Depends(_versione_attesa)]
