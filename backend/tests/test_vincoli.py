"""Vincoli dello schema: la rete di sicurezza anche se il codice applicativo sbaglia."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from academy_hub.db.modelli import EventoAudit, Persona
from academy_hub.dominio.stati import StatoIscrizione

from .dati import crea_edizione, crea_iscrizione, crea_persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione


@pytest.mark.parametrize("stato", [S.RICHIESTA, S.APPROVATA, S.IN_ATTESA, S.CONFERMATA])
def test_r1_seconda_iscrizione_attiva_rifiutata(db: Engine, stato: StatoIscrizione) -> None:
    with Session(db) as sessione:
        anna = crea_persona(sessione, "Anna")
        edizione = crea_edizione(sessione)
        crea_iscrizione(sessione, anna, edizione, stato)

        with pytest.raises(IntegrityError, match="uq_iscrizioni_attiva"):
            crea_iscrizione(sessione, anna, edizione)


@pytest.mark.parametrize("stato", [S.RIFIUTATA, S.ANNULLATA])
def test_d4_nuova_richiesta_dopo_rifiuto_o_annullamento(db: Engine, stato: StatoIscrizione) -> None:
    with Session(db) as sessione:
        anna = crea_persona(sessione, "Anna")
        edizione = crea_edizione(sessione)
        crea_iscrizione(sessione, anna, edizione, stato)

        crea_iscrizione(sessione, anna, edizione)
        sessione.commit()


@pytest.mark.parametrize(
    ("capienza", "posti_confermati", "vincolo"),
    [
        (0, 0, "ck_edizioni_capienza_positiva"),
        (2, 3, "ck_edizioni_posti_entro_capienza"),
        (2, -1, "ck_edizioni_posti_entro_capienza"),
    ],
)
def test_capienza_e_posti(db: Engine, capienza: int, posti_confermati: int, vincolo: str) -> None:
    with Session(db) as sessione, pytest.raises(IntegrityError, match=vincolo):
        crea_edizione(sessione, capienza=capienza, posti_confermati=posti_confermati)


def test_r3_il_database_non_supera_la_capienza(db: Engine) -> None:
    with Session(db) as sessione:
        edizione = crea_edizione(sessione, capienza=1, posti_confermati=1)
        sessione.commit()

        with pytest.raises(IntegrityError, match="ck_edizioni_posti_entro_capienza"):
            sessione.execute(
                text("UPDATE edizioni SET posti_confermati = posti_confermati + 1 WHERE id = :id"),
                {"id": edizione.id},
            )


def test_stato_sconosciuto_rifiutato(db: Engine) -> None:
    with Session(db) as sessione:
        iscrizione = crea_iscrizione(
            sessione, crea_persona(sessione, "Anna"), crea_edizione(sessione)
        )

        with pytest.raises(IntegrityError, match="ck_iscrizioni_stato_valido"):
            sessione.execute(
                text("UPDATE iscrizioni SET stato = 'Sospesa' WHERE id = :id"),
                {"id": iscrizione.id},
            )


def test_stato_approvato_richiede_la_data_di_approvazione(db: Engine) -> None:
    with Session(db) as sessione:
        iscrizione = crea_iscrizione(
            sessione, crea_persona(sessione, "Anna"), crea_edizione(sessione)
        )

        with pytest.raises(IntegrityError, match="ck_iscrizioni_approvata_con_data"):
            sessione.execute(
                text("UPDATE iscrizioni SET stato = 'Approvata' WHERE id = :id"),
                {"id": iscrizione.id},
            )


def test_ruolo_sconosciuto_rifiutato(db: Engine) -> None:
    with Session(db) as sessione:
        anna = crea_persona(sessione, "Anna")
        anna.ruoli = ["dipendente", "superutente"]

        with pytest.raises(IntegrityError, match="ck_persone_ruoli_validi"):
            sessione.flush()


def test_persona_ha_il_ruolo_dipendente_per_impostazione(db: Engine) -> None:
    with Session(db) as sessione:
        anna_id = crea_persona(sessione, "Anna").id
        sessione.commit()

    with Session(db) as sessione:
        assert sessione.get_one(Persona, anna_id).ruoli == ["dipendente"]


@pytest.mark.parametrize(
    "istruzione",
    [
        "UPDATE eventi_audit SET motivo = 'ritoccato'",
        "DELETE FROM eventi_audit",
        "TRUNCATE eventi_audit CASCADE",
    ],
)
def test_r6_eventi_di_audit_immutabili(db: Engine, istruzione: str) -> None:
    with Session(db) as sessione:
        iscrizione = crea_iscrizione(
            sessione, crea_persona(sessione, "Anna"), crea_edizione(sessione)
        )
        sessione.add(EventoAudit(iscrizione_id=iscrizione.id, stato_a=S.RICHIESTA))
        sessione.flush()

        with pytest.raises(DBAPIError, match="sola aggiunta"):
            sessione.execute(text(istruzione))
