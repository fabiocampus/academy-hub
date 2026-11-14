"""Dati demo locali (`academy_hub.db.demo`) e realm Keycloak devono restare allineati."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.db import demo
from academy_hub.db.modelli import Edizione, Persona, Team
from academy_hub.repository import persone

REALM = Path(__file__).parents[2] / "keycloak" / "realm-academy.json"


def _realm() -> dict[str, Any]:
    return json.loads(REALM.read_text(encoding="utf-8"))


def test_ogni_persona_demo_ha_un_utente_keycloak_con_la_stessa_email() -> None:
    utenti = {u["username"]: u for u in _realm()["users"]}

    for p in demo.PERSONE:
        assert utenti[p.utente]["email"] == p.email
        assert utenti[p.utente]["emailVerified"] is True


def test_ogni_utente_keycloak_e_una_persona_demo_o_dichiaratamente_esterno() -> None:
    utenti = {u["username"] for u in _realm()["users"]}

    assert utenti == {p.utente for p in demo.PERSONE} | set(demo.UTENTI_SENZA_PERSONA)


def test_realm_solo_dati_sintetici() -> None:
    """Repository pubblico: email solo sul dominio riservato .example (RFC 2606)."""
    assert all(u["email"].endswith("@academy.example") for u in _realm()["users"])


def test_client_del_realm_mettono_il_pubblico_dell_api() -> None:
    for client in _realm()["clients"]:
        pubblici = [
            m["config"]["included.custom.audience"]
            for m in client["protocolMappers"]
            if m["protocolMapper"] == "oidc-audience-mapper"
        ]
        assert pubblici == ["academy-api"], client["clientId"]


def test_client_web_solo_codice_con_pkce() -> None:
    web = next(c for c in _realm()["clients"] if c["clientId"] == "academy-web")

    assert web["publicClient"] is True
    assert web["directAccessGrantsEnabled"] is False
    assert web["implicitFlowEnabled"] is False
    assert web["attributes"]["pkce.code.challenge.method"] == "S256"


@pytest.mark.integrazione
def test_carica_una_volta_sola(db: Engine) -> None:
    assert demo.carica(db, da=date(2030, 1, 7)) is True
    assert demo.carica(db, da=date(2030, 1, 7)) is False

    with Session(db) as sessione:
        assert sessione.scalar(select(func.count()).select_from(Persona)) == len(demo.PERSONE)
        assert sessione.scalar(select(func.count()).select_from(Team)) == len(demo.TEAM)
        assert sessione.scalar(select(func.count()).select_from(Edizione)) == 3


@pytest.mark.integrazione
def test_organigramma_demo(db: Engine) -> None:
    demo.carica(db, da=date(2030, 1, 7))

    with Session(db) as sessione:
        id_di = {p.email: p.id for p in sessione.scalars(select(Persona))}
        dario = persone.attore_per_email(sessione, "dipendente@academy.example")
        assert dario is not None
        catena = persone.catena_responsabili(sessione, dario.persona_id)
        admin = persone.attore_per_email(sessione, "admin@academy.example")

    assert catena == [
        id_di["responsabile@academy.example"],
        id_di["dirigente@academy.example"],
    ]
    assert admin is not None and {r.value for r in admin.ruoli} == {"dipendente", "admin_academy"}
