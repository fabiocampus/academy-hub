"""Evento iCalendar (RFC 5545) di un'edizione confermata: Python puro, senza database.

Un'edizione dura giorni interi: l'evento è "tutto il giorno" (`VALUE=DATE`), senza fuso,
e `DTEND` è il giorno dopo l'ultimo, perché in iCalendar la fine è esclusa.
L'`UID` dipende solo dall'iscrizione: scaricare di nuovo il file aggiorna l'evento già
importato invece di duplicarlo (se le date dell'edizione cambiano, cresce `SEQUENCE`).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

PRODID = "-//Academy Hub//Iscrizioni//IT"
_LUNGHEZZA_RIGA = 75  # ottetti, CRLF escluso (RFC 5545 §3.1)


@dataclass(frozen=True)
class EventoEdizione:
    iscrizione_id: int
    titolo: str
    descrizione: str
    data_inizio: date
    data_fine: date
    versione: int
    """Versione dell'edizione: diventa `SEQUENCE`, così un client sa che l'evento è cambiato."""


def escape(valore: str) -> str:
    """Escape di un valore TEXT (RFC 5545 §3.3.11): barra, punto e virgola, virgola, a capo."""
    return (
        valore.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def piega(riga: str) -> list[str]:
    """Righe di al massimo 75 ottetti UTF-8; le continuazioni iniziano con uno spazio.

    Si taglia fra un carattere e l'altro, mai dentro una sequenza UTF-8.
    """
    parti: list[str] = []
    corrente = ""
    for carattere in riga:
        # Lo spazio iniziale delle continuazioni conta nei 75 ottetti.
        if len((corrente + carattere).encode()) > _LUNGHEZZA_RIGA:
            parti.append(corrente)
            corrente = " "
        corrente += carattere
    parti.append(corrente)
    return parti


def _data(giorno: date) -> str:
    return giorno.strftime("%Y%m%d")


def calendario(evento: EventoEdizione, adesso: datetime) -> str:
    """Il file `.ics` completo, con CRLF come chiede lo standard."""
    stamp = adesso.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    righe = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:iscrizione-{evento.iscrizione_id}@academy-hub",
        f"DTSTAMP:{stamp}",
        f"SEQUENCE:{max(evento.versione - 1, 0)}",
        f"DTSTART;VALUE=DATE:{_data(evento.data_inizio)}",
        f"DTEND;VALUE=DATE:{_data(evento.data_fine + timedelta(days=1))}",
        f"SUMMARY:{escape(evento.titolo)}",
        f"DESCRIPTION:{escape(evento.descrizione)}",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "".join(f"{parte}\r\n" for riga in righe for parte in piega(riga))
