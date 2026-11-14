"""Ruoli applicativi (CONTEXT.md). Una persona può averne più di uno."""

from enum import StrEnum


class Ruolo(StrEnum):
    DIPENDENTE = "dipendente"
    RESPONSABILE = "responsabile"
    ADMIN_ACADEMY = "admin_academy"
    DOCENTE = "docente"
