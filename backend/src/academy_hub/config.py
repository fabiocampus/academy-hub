"""Configurazione letta solo dalle variabili d'ambiente (prefisso ``ACADEMY_``)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["locale", "collaudo", "produzione"]
Identita = Literal["oidc", "databricks", "provvisoria"]


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACADEMY_", extra="ignore")

    ambiente: Ambiente = "locale"
    # Valore di sviluppo per il PostgreSQL di docker compose; negli altri ambienti
    # arriva dalla piattaforma. Mai credenziali reali qui.
    database_url: str = "postgresql+psycopg://academy:academy@localhost:5432/academy"
    livello_log: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Da dove arriva l'identità (ADR-0008):
    # - oidc: token Bearer di un provider OIDC (Keycloak in locale);
    # - databricks: header X-Forwarded-Email messo dal proxy di Databricks Apps; fidarsi
    #   di un header ha senso solo dietro quel proxy, quindi è vietato in locale;
    # - provvisoria: header X-Persona-Id (fase 5), permette di impersonare chiunque:
    #   solo in locale, lo usano i test.
    identita: Identita = "oidc"
    oidc_emittente: str = "http://localhost:8080/realms/academy"
    # Dentro docker compose il backend raggiunge Keycloak come "keycloak", mentre
    # l'emittente nei token resta localhost: per questo le chiavi hanno un URL a parte.
    oidc_jwks_url: str | None = None
    oidc_pubblico: str = "academy-api"
    # Client pubblico del frontend (PKCE): il browser lo legge da GET /api/v1/configurazione.
    oidc_client_web: str = "academy-web"
    # R5: un'iscrizione Confermata si annulla solo se mancano più di N giorni all'inizio.
    scadenza_annullamento_giorni: int = Field(default=3, ge=0, le=365)

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_emittente}/protocol/openid-connect/certs"

    @model_validator(mode="after")
    def _identita_coerente_con_ambiente(self) -> Self:
        if self.identita == "provvisoria" and self.ambiente != "locale":
            raise ValueError(
                f"identita=provvisoria non è ammessa con ambiente={self.ambiente!r}: solo in locale"
            )
        if self.identita == "databricks" and self.ambiente == "locale":
            raise ValueError(
                "identita=databricks non è ammessa in locale: senza il proxy di Databricks Apps "
                "chiunque può scrivere X-Forwarded-Email"
            )
        if self.identita == "oidc" and self.ambiente != "locale":
            for nome, url in (("oidc_emittente", self.oidc_emittente), ("jwks", self.jwks_url)):
                if not url.startswith("https://"):
                    raise ValueError(
                        f"{nome} deve essere https fuori dal locale: le chiavi lette in chiaro "
                        "si possono sostituire"
                    )
        return self


@lru_cache
def impostazioni() -> Impostazioni:
    return Impostazioni()
