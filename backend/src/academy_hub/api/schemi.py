"""Schemi Pydantic di richieste e risposte: la forma pubblica del contratto OpenAPI."""

from datetime import date, datetime
from typing import Annotated, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from academy_hub.dominio.stati import StatoIscrizione

T = TypeVar("T")

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


def _non_null(valore: T | None) -> T:
    """Un campo assente resta invariato; `null` esplicito non ha senso dove serve un valore."""
    if valore is None:
        raise ValueError("non può essere null")
    return valore


class ModificaCorso(BaseModel):
    """Solo i campi presenti vengono modificati."""

    model_config = ConfigDict(extra="forbid")

    titolo: Titolo | None = None
    descrizione: str | None = None
    durata_ore: OrePositive | None = None

    _senza_null = field_validator("titolo", "descrizione", "durata_ore")(_non_null)


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

    _senza_null = field_validator("data_inizio", "data_fine", "capienza")(_non_null)


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


# --- Iscrizioni (US-04..US-11) -----------------------------------------------------

Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class NuovaIscrizione(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edizione_id: int


class IscrizioneLetta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    edizione_id: int
    stato: StatoIscrizione
    richiesta_il: datetime
    approvata_il: datetime | None
    aggiornata_il: datetime = Field(description="Ultimo cambio di stato")


class EventoLetto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stato_da: StatoIscrizione | None = Field(description="null alla nascita dell'iscrizione")
    stato_a: StatoIscrizione
    autore_id: int | None = Field(description="null = il sistema")
    motivo: str | None
    avvenuto_il: datetime


class IscrizioneConStoria(IscrizioneLetta):
    storia: list[EventoLetto] = Field(description="Cambi di stato in ordine cronologico (R6)")


class VoceMiaIscrizione(IscrizioneLetta):
    corso: CorsoInBreve
    data_inizio: date
    data_fine: date
    posizione_lista_attesa: int | None = Field(
        description="Posizione in lista d'attesa (1 = la prossima), solo se InAttesa"
    )


class PaginaMieIscrizioni(BaseModel):
    elementi: list[VoceMiaIscrizione]
    totale: int
    limite: int
    offset: int


class Rifiuto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Motivo


class PersonaInBreve(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class RichiestaDaApprovare(BaseModel):
    iscrizione_id: int
    persona: PersonaInBreve
    edizione_id: int
    corso: CorsoInBreve
    data_inizio: date
    richiesta_il: datetime


class PaginaRichieste(BaseModel):
    elementi: list[RichiestaDaApprovare]
    totale: int
    limite: int
    offset: int
