"""Configurazione letta solo dalle variabili d'ambiente (prefisso ``ACADEMY_``)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["locale", "collaudo", "produzione"]


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACADEMY_", extra="ignore")

    ambiente: Ambiente = "locale"
    # Valore di sviluppo per il PostgreSQL di docker compose; negli altri ambienti
    # arriva dalla piattaforma. Mai credenziali reali qui.
    database_url: str = "postgresql+psycopg://academy:academy@localhost:5432/academy"
    livello_log: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Header `X-Persona-Id` al posto del token (fase 5, ADR-0005): permette di
    # impersonare chiunque, quindi va acceso esplicitamente e solo in locale.
    identita_provvisoria: bool = False

    @model_validator(mode="after")
    def _identita_provvisoria_solo_in_locale(self) -> Self:
        if self.identita_provvisoria and self.ambiente != "locale":
            raise ValueError(
                f"identita_provvisoria non è ammessa con ambiente={self.ambiente!r}: solo in locale"
            )
        return self


@lru_cache
def impostazioni() -> Impostazioni:
    return Impostazioni()
