"""Modelli SQLAlchemy dello schema transazionale.

Lo schema reale lo creano le migrazioni Alembic in `schema/versions/`; questi modelli
devono restare allineati (lo verifica `alembic check` nei test).

Vincoli nel database, come rete di sicurezza anche se il codice sbaglia:
- R1: indice `UNIQUE` parziale su (persona, edizione) per le iscrizioni attive;
- R3: `posti_confermati` fra 0 e `capienza`, aggiornato solo con l'edizione bloccata;
- R6: `eventi_audit` è immutabile: trigger su UPDATE, DELETE e TRUNCATE (migrazione iniziale).
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from academy_hub.dominio.ruoli import Ruolo
from academy_hub.dominio.stati import STATI_ATTIVI, StatoIscrizione

CONVENZIONE_NOMI = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENZIONE_NOMI)


def elenco_sql(valori: list[str]) -> str:
    """`'a', 'b'` per le clausole IN dei vincoli: solo valori costanti del codice."""
    return ", ".join(f"'{v}'" for v in sorted(valori))


STATI = elenco_sql([s.value for s in StatoIscrizione])
ATTIVI = elenco_sql([s.value for s in STATI_ATTIVI])
APPROVATI = elenco_sql(
    [
        StatoIscrizione.APPROVATA,
        StatoIscrizione.IN_ATTESA,
        StatoIscrizione.CONFERMATA,
        StatoIscrizione.COMPLETATA,
    ]
)
RUOLI = elenco_sql([r.value for r in Ruolo])


def _valori(enum: type[StatoIscrizione]) -> list[str]:
    return [s.value for s in enum]


def tipo_stato() -> Enum:
    """Stato salvato come testo (il valore dell'Enum); il CHECK è esplicito nella tabella."""
    return Enum(
        StatoIscrizione,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=_valori,
    )


class Team(Base):
    __tablename__ = "team"
    __table_args__ = (CheckConstraint("team_padre_id <> id", name="non_padre_di_se"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)
    team_padre_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))
    # Facoltativo solo per poter creare il team prima del suo responsabile.
    responsabile_id: Mapped[int | None] = mapped_column(ForeignKey("persone.id", use_alter=True))


class Persona(Base):
    __tablename__ = "persone"
    __table_args__ = (
        CheckConstraint(
            f"cardinality(ruoli) > 0 AND ruoli <@ ARRAY[{RUOLI}]::varchar[]",
            name="ruoli_validi",
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"), index=True)
    ruoli: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), server_default=text("ARRAY['dipendente']::varchar[]")
    )


class Corso(Base):
    __tablename__ = "corsi"
    __table_args__ = (CheckConstraint("durata_ore > 0", name="durata_positiva"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    titolo: Mapped[str] = mapped_column(String(200))
    descrizione: Mapped[str] = mapped_column(Text, server_default="")
    durata_ore: Mapped[int]


class Edizione(Base):
    __tablename__ = "edizioni"
    __table_args__ = (
        CheckConstraint("capienza > 0", name="capienza_positiva"),
        CheckConstraint("data_fine >= data_inizio", name="date_ordinate"),
        CheckConstraint("posti_confermati BETWEEN 0 AND capienza", name="posti_entro_capienza"),
        # Catalogo: edizioni non cancellate per data di inizio.
        Index(
            "ix_edizioni_catalogo", "data_inizio", postgresql_where=text("cancellata_il IS NULL")
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    corso_id: Mapped[int] = mapped_column(ForeignKey("corsi.id"), index=True)
    data_inizio: Mapped[date] = mapped_column(Date)
    data_fine: Mapped[date] = mapped_column(Date)
    capienza: Mapped[int]
    posti_confermati: Mapped[int] = mapped_column(server_default="0")
    docente_id: Mapped[int | None] = mapped_column(ForeignKey("persone.id"))
    # Cancellazione logica (D10): l'edizione resta, le iscrizioni attive diventano Annullata.
    cancellata_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Iscrizione(Base):
    __tablename__ = "iscrizioni"
    __table_args__ = (
        CheckConstraint(f"stato IN ({STATI})", name="stato_valido"),
        CheckConstraint(
            f"stato NOT IN ({APPROVATI}) OR approvata_il IS NOT NULL",
            name="approvata_con_data",
        ),
        # R1: al massimo una iscrizione attiva per persona ed edizione.
        Index(
            "uq_iscrizioni_attiva",
            "persona_id",
            "edizione_id",
            unique=True,
            postgresql_where=text(f"stato IN ({ATTIVI})"),
        ),
        # R4: lista d'attesa di un'edizione in ordine di approvazione (id come spareggio).
        Index(
            "ix_iscrizioni_lista_attesa",
            "edizione_id",
            "approvata_il",
            "id",
            postgresql_where=text("stato = 'InAttesa'"),
        ),
        Index("ix_iscrizioni_edizione_stato", "edizione_id", "stato"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persone.id"), index=True)
    edizione_id: Mapped[int] = mapped_column(ForeignKey("edizioni.id"))
    stato: Mapped[StatoIscrizione] = mapped_column(tipo_stato())
    richiesta_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approvata_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggiornata_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EventoAudit(Base):
    __tablename__ = "eventi_audit"
    __table_args__ = (
        CheckConstraint(f"stato_da IS NULL OR stato_da IN ({STATI})", name="stato_da_valido"),
        CheckConstraint(f"stato_a IN ({STATI})", name="stato_a_valido"),
        Index("ix_eventi_audit_iscrizione", "iscrizione_id", "avvenuto_il"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    iscrizione_id: Mapped[int] = mapped_column(ForeignKey("iscrizioni.id"))
    # NULL = il «sistema» (job di promozione e di scadenza).
    autore_id: Mapped[int | None] = mapped_column(ForeignKey("persone.id"))
    stato_da: Mapped[StatoIscrizione | None] = mapped_column(tipo_stato())
    stato_a: Mapped[StatoIscrizione] = mapped_column(tipo_stato())
    motivo: Mapped[str | None] = mapped_column(Text)
    avvenuto_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
