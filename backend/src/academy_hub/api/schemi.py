"""Schemi Pydantic di richieste e risposte: la forma pubblica del contratto OpenAPI."""

from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from academy_hub.dominio.stati import StatoIscrizione

Titolo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OrePositive = Annotated[int, Field(gt=0, le=1000)]
Capienza = Annotated[int, Field(gt=0, le=10_000)]


class NuovoCorso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titolo: Titolo
    descrizione: str = ""
    durata_ore: OrePositive


class CorsoLetto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titolo: str
    descrizione: str
    durata_ore: int
    archiviato_il: datetime | None


class ModificaCorso(BaseModel):
    """Solo i campi presenti vengono modificati."""

    model_config = ConfigDict(extra="forbid")

    titolo: Titolo | None = None
    descrizione: str | None = None
    durata_ore: OrePositive | None = None


class NuovaEdizione(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corso_id: int
    data_inizio: date
    data_fine: date
    capienza: Capienza
    docente_id: int | None = None

    @field_validator("data_fine")
    @classmethod
    def _fine_dopo_inizio(cls, data_fine: date, info: ValidationInfo) -> date:
        inizio = info.data.get("data_inizio")
        if isinstance(inizio, date) and data_fine < inizio:
            raise ValueError("la data di fine precede quella di inizio")
        return data_fine


class ModificaEdizione(BaseModel):
    """Solo i campi presenti vengono modificati; le date si confrontano con quelle salvate."""

    model_config = ConfigDict(extra="forbid")

    data_inizio: date | None = None
    data_fine: date | None = None
    capienza: Capienza | None = None
    docente_id: int | None = Field(
        default=None, description="Assente: invariato; null: toglie il docente"
    )


class EdizioneLetta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    corso_id: int
    data_inizio: date
    data_fine: date
    capienza: int
    posti_confermati: int
    docente_id: int | None
    cancellata_il: datetime | None


class CorsoInBreve(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titolo: str
    durata_ore: int


class MiaIscrizione(BaseModel):
    stato: StatoIscrizione


class VoceCatalogo(BaseModel):
    edizione_id: int
    corso: CorsoInBreve
    data_inizio: date
    data_fine: date
    capienza: int
    posti_confermati: int
    lista_attesa: int = Field(description="Iscrizioni InAttesa dell'edizione")
    mia_iscrizione: MiaIscrizione | None = Field(
        description="La mia iscrizione attiva all'edizione, se c'è"
    )


class PaginaCatalogo(BaseModel):
    elementi: list[VoceCatalogo]
    totale: int
    limite: int
    offset: int
