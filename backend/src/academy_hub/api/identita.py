"""Da dove arriva l'identità di chi chiama l'API (ADR-0008).

Ogni provider legge gli header della richiesta e dice *chi* è la persona, senza ruoli:
ruoli e team li decide l'applicazione e stanno nel database (`repository.persone`).
Così lo stesso codice di autorizzazione (i servizi) funziona sopra Keycloak in locale e
sopra l'identità che Databricks Apps passa all'App.
"""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from academy_hub.config import Impostazioni
from academy_hub.dominio.errori import ErroreDominio, NonAutenticato

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PerEmail:
    email: str


@dataclass(frozen=True)
class PerId:
    persona_id: int


Identificazione = PerEmail | PerId


class IdentitaNonDisponibile(ErroreDominio):
    """Il provider d'identità non risponde: non si può dire se il token è valido."""

    tipo = "identita-non-disponibile"
    titolo = "Servizio d'identità non raggiungibile"


class ProviderIdentita(Protocol):
    def identifica(self, intestazioni: Mapping[str, str]) -> Identificazione:
        """Chi è la persona; `NonAutenticato` se l'identità manca o non è valida.

        `intestazioni` non distingue maiuscole e minuscole (come quelle di Starlette).
        """
        ...


# Basta a scartare valori assurdi; la verifica vera è il confronto con il database.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


def _email(valore: object) -> str:
    if not isinstance(valore, str) or not _EMAIL.match(valore):
        raise NonAutenticato("Email mancante o non valida nell'identità")
    # Le email in `persone` sono minuscole (vincolo email_minuscola).
    return valore.lower()


TrovaChiave = Callable[[str], Any]
"""Dato il token, la chiave pubblica che lo deve aver firmato (dal JWKS, per `kid`).

Solleva `IdentitaNonDisponibile` se le chiavi non si possono leggere (il client non ha
colpa: 503) e `jwt.PyJWTError` se il token non indica una chiave del provider (401).
"""

# Guasti del JWKS: irraggiungibile o HTTP in errore (PyJWKClientConnectionError), corpo
# non JSON (ValueError), non un oggetto o senza chiavi di firma (PyJWKClientError),
# chiavi inutilizzabili (PyJWKSetError).
_GUASTI_JWKS = (jwt.PyJWKClientError, jwt.PyJWKSetError, ValueError)


def chiavi_da_jwks(jwks_url: str, durata_cache_s: float = 300) -> TrovaChiave:
    """Chiavi dal JWKS del provider, con il JWK Set in cache per `durata_cache_s`.

    Niente cache per singola chiave (`cache_keys` di PyJWT non scade mai): una chiave
    tolta dal JWKS, perché ruotata o compromessa, smette di valere entro `durata_cache_s`.
    Un `kid` sconosciuto fa rileggere il JWKS (rotazione), al più ogni 30 secondi.
    """
    client = jwt.PyJWKClient(jwks_url, lifespan=durata_cache_s, timeout=5)

    def trova_chiave(token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        if not isinstance(kid, str):
            raise jwt.InvalidTokenError("kid mancante nell'header del token")
        try:
            client.get_signing_keys()
        except _GUASTI_JWKS as errore:
            raise IdentitaNonDisponibile("Chiavi del provider d'identità non leggibili") from errore
        try:
            return client.get_signing_key(kid).key
        except (jwt.PyJWKClientConnectionError, jwt.PyJWKSetError, ValueError) as errore:
            # Il JWKS si è guastato proprio nella rilettura per un kid nuovo.
            raise IdentitaNonDisponibile("Chiavi del provider d'identità non leggibili") from errore
        # Resta PyJWKClientError: nessuna chiave con quel kid, anche dopo la rilettura.

    return trova_chiave


class Oidc:
    """Token Bearer (JWT) di un provider OIDC: firma, emittente, pubblico e scadenza.

    Accetta solo RS256: niente `none` né algoritmi simmetrici scelti da chi manda il token.
    L'email deve essere verificata dal provider, perché è la chiave verso `persone`.
    """

    ALGORITMI = ("RS256",)
    TOLLERANZA_OROLOGIO_S = 30

    def __init__(self, emittente: str, pubblico: str, trova_chiave: TrovaChiave) -> None:
        self._emittente = emittente
        self._pubblico = pubblico
        self._trova_chiave = trova_chiave

    @classmethod
    def da_jwks(cls, emittente: str, pubblico: str, jwks_url: str) -> "Oidc":
        return cls(emittente, pubblico, chiavi_da_jwks(jwks_url))

    def identifica(self, intestazioni: Mapping[str, str]) -> Identificazione:
        token = _bearer(intestazioni.get("authorization"))
        try:
            chiave = self._trova_chiave(token)
            dati: dict[str, Any] = jwt.decode(
                token,
                chiave,
                algorithms=list(self.ALGORITMI),
                audience=self._pubblico,
                issuer=self._emittente,
                leeway=self.TOLLERANZA_OROLOGIO_S,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWKClientConnectionError as errore:
            raise IdentitaNonDisponibile("Chiavi del provider d'identità non raggiungibili") from (
                errore
            )
        except jwt.PyJWTError as errore:
            # Il motivo esatto (pubblico, emittente, kid attesi) resta nel log, non nella
            # risposta.
            log.info("Token rifiutato: %s", errore)
            raise NonAutenticato("Token non valido") from errore
        if dati.get("email_verified") is not True:
            raise NonAutenticato("L'email del token non è verificata dal provider")
        return PerEmail(_email(dati.get("email")))


def _bearer(valore: str | None) -> str:
    if valore is None:
        raise NonAutenticato("Identità mancante: serve Authorization: Bearer <token>")
    schema, _, token = valore.strip().partition(" ")
    if schema.lower() != "bearer" or not token.strip():
        raise NonAutenticato("Authorization deve essere Bearer <token>")
    return token.strip()


class Databricks:
    """Identità dell'utente passata da Databricks Apps nell'header `X-Forwarded-Email`.

    Il proxy dell'App autentica l'utente e imposta l'header: l'App non è raggiungibile
    altrimenti. Per questo il provider è vietato in locale (`config`).
    """

    def identifica(self, intestazioni: Mapping[str, str]) -> Identificazione:
        valore = intestazioni.get("x-forwarded-email")
        if valore is None:
            raise NonAutenticato("Identità mancante: nessun X-Forwarded-Email dalla piattaforma")
        return PerEmail(_email(valore))


_PERSONA_ID = re.compile(r"^[1-9]\d{0,18}$")


class Provvisoria:
    """Header `X-Persona-Id` della fase 5: solo in locale, per i test (ADR-0005, ADR-0008)."""

    def identifica(self, intestazioni: Mapping[str, str]) -> Identificazione:
        valore = intestazioni.get("x-persona-id")
        if valore is None:
            raise NonAutenticato("Identità mancante")
        if not _PERSONA_ID.match(valore):
            raise NonAutenticato("Identità non valida")
        return PerId(int(valore))


def provider(impostazioni: Impostazioni) -> ProviderIdentita:
    match impostazioni.identita:
        case "oidc":
            return Oidc.da_jwks(
                impostazioni.oidc_emittente, impostazioni.oidc_pubblico, impostazioni.jwks_url
            )
        case "databricks":
            return Databricks()
        case "provvisoria":
            return Provvisoria()
