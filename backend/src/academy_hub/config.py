"""Configurazione letta solo dalle variabili d'ambiente (prefisso ``ACADEMY_``)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Ambiente = Literal["locale", "collaudo", "produzione"]


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACADEMY_", extra="ignore")

    ambiente: Ambiente = "locale"
    # Valore di sviluppo per il PostgreSQL di docker compose; negli altri ambienti
    # arriva dalla piattaforma. Mai credenziali reali qui.
    database_url: str = "postgresql+psycopg://academy:academy@localhost:5432/academy"
    livello_log: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def impostazioni() -> Impostazioni:
    return Impostazioni()
