"""Evento iCalendar dell'edizione confermata (issue #86), RFC 5545."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from academy_hub.dominio.ics import EventoEdizione, calendario, escape, piega

ADESSO = datetime(2026, 11, 15, 13, 30, 5, tzinfo=timezone(timedelta(hours=1)))


BASE = EventoEdizione(
    iscrizione_id=42,
    titolo="SQL avanzato",
    descrizione="Finestre, CTE; piani",
    data_inizio=date(2026, 12, 1),
    data_fine=date(2026, 12, 2),
    versione=1,
)


def _evento(**modifiche: Any) -> EventoEdizione:
    return replace(BASE, **modifiche)


def _proprieta(ics: str) -> dict[str, str]:
    """Righe ricomposte (piegatura tolta) come nome -> valore."""
    srotolato = ics.replace("\r\n ", "")
    return dict(riga.split(":", 1) for riga in srotolato.split("\r\n") if riga)


def test_evento_tutto_il_giorno_con_fine_esclusa() -> None:
    p = _proprieta(calendario(_evento(), ADESSO))
    assert p["DTSTART;VALUE=DATE"] == "20261201"
    assert p["DTEND;VALUE=DATE"] == "20261203"


def test_struttura_e_identita_stabile() -> None:
    ics = calendario(_evento(), ADESSO)
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert ics.endswith("END:VEVENT\r\nEND:VCALENDAR\r\n")
    p = _proprieta(ics)
    assert p["UID"] == "iscrizione-42@academy-hub"
    assert p["DTSTAMP"] == "20261115T123005Z"  # in UTC
    assert p["SEQUENCE"] == "0"
    assert p["SUMMARY"] == "SQL avanzato"
    assert p["DESCRIPTION"] == "Finestre\\, CTE\\; piani"


def test_sequence_cresce_con_la_versione_dell_edizione() -> None:
    assert _proprieta(calendario(_evento(versione=4), ADESSO))["SEQUENCE"] == "3"


def test_ogni_riga_finisce_con_crlf() -> None:
    ics = calendario(_evento(descrizione="riga uno\nriga due"), ADESSO)
    assert "\n" not in ics.replace("\r\n", "")
    assert _proprieta(ics)["DESCRIPTION"] == "riga uno\\nriga due"


def test_escape_del_testo() -> None:
    assert escape("a\\b;c,d\r\ne\nf") == "a\\\\b\\;c\\,d\\ne\\nf"


def test_piegatura_a_75_ottetti_senza_spezzare_utf8() -> None:
    riga = "DESCRIPTION:" + "è" * 100
    parti = piega(riga)
    assert len(parti) > 1
    assert all(len(p.encode()) <= 75 for p in parti)
    assert all(p.startswith(" ") for p in parti[1:])
    assert "".join(p.removeprefix(" ") if i else p for i, p in enumerate(parti)) == riga


def test_riga_corta_non_si_piega() -> None:
    assert piega("SUMMARY:SQL") == ["SUMMARY:SQL"]


def test_titolo_lungo_piegato_nel_file() -> None:
    ics = calendario(_evento(titolo="Corso " * 30), ADESSO)
    assert all(len(r.encode()) <= 75 for r in ics.split("\r\n"))
    assert _proprieta(ics)["SUMMARY"] == ("Corso " * 30)


def test_adesso_senza_fuso_esplicito_in_utc() -> None:
    p = _proprieta(calendario(_evento(), datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)))
    assert p["DTSTAMP"] == "20260102T030405Z"
