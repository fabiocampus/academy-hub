"""Il calendario del dominio è quello di Roma (D11), qualunque sia il fuso del server."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")


def oggi() -> date:
    return datetime.now(FUSO).date()
