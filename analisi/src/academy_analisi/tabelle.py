"""Le tabelle di Lakebase storicizzate in Unity Catalog, con le colonne lette (ADR-0016).

Colonne esplicite, non `SELECT *`: una colonna nuova dell'App (magari un dato personale)
non arriva nei dati analitici finché qualcuno non la aggiunge qui. Un test del backend
(`backend/tests/test_contratto_analisi.py`) controlla che esistano nel modello SQLAlchemy.

Fuori: `versione` (concorrenza ottimistica dell'API, ADR-0005), `chiave_idempotenza`
(valore scelto dal client, ADR-0006) e `eventi_audit` (registro solo in aggiunta: lo
storico delle iscrizioni lo dà già lo SCD di tipo 2).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tabella:
    nome: str
    colonne: tuple[str, ...]
    chiave: tuple[str, ...] = ("id",)


TABELLE: tuple[Tabella, ...] = (
    Tabella("team", ("id", "nome", "team_padre_id", "responsabile_id")),
    Tabella("persone", ("id", "nome", "email", "team_id", "ruoli")),
    Tabella("corsi", ("id", "titolo", "descrizione", "durata_ore", "archiviato_il")),
    Tabella(
        "edizioni",
        (
            "id",
            "corso_id",
            "data_inizio",
            "data_fine",
            "capienza",
            "posti_confermati",
            "docente_id",
            "cancellata_il",
        ),
    ),
    Tabella(
        "iscrizioni",
        (
            "id",
            "persona_id",
            "edizione_id",
            "stato",
            "richiesta_il",
            "approvata_il",
            "aggiornata_il",
        ),
    ),
)
