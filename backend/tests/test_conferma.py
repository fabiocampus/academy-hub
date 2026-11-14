"""Conferma del posto (US-08): R3 anche con conferme simultanee, R6 a ogni cambio di stato."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from academy_hub.db.modelli import Edizione, Iscrizione
from academy_hub.dominio.errori import EdizioneCancellata
from academy_hub.dominio.stati import StatoIscrizione, TransizioneNonConsentita
from academy_hub.repository.iscrizioni import IscrizioneNonTrovata, eventi_audit
from academy_hub.servizi.iscrizioni import conferma_posto

from .dati import crea_edizione, crea_iscrizione, crea_persona

pytestmark = pytest.mark.integrazione

S = StatoIscrizione


def prepara(
    db: Engine, capienza: int, posti_confermati: int, approvate: int
) -> tuple[int, list[int], int]:
    """Edizione con `approvate` iscrizioni Approvata; restituisce (edizione, iscrizioni, admin)."""
    with Session(db) as sessione:
        admin = crea_persona(sessione, "Admin")
        edizione = crea_edizione(sessione, capienza=capienza, posti_confermati=posti_confermati)
        iscrizioni = [
            crea_iscrizione(
                sessione, crea_persona(sessione, f"Dipendente{n}"), edizione, S.APPROVATA
            ).id
            for n in range(approvate)
        ]
        sessione.commit()
        return edizione.id, iscrizioni, admin.id


def conferma(db: Engine, iscrizione_id: int, autore_id: int) -> StatoIscrizione:
    with Session(db) as sessione, sessione.begin():
        return conferma_posto(sessione, iscrizione_id, autore_id)


def test_con_posti_liberi_diventa_confermata(db: Engine) -> None:
    edizione_id, [iscrizione_id], admin_id = prepara(
        db, capienza=2, posti_confermati=0, approvate=1
    )

    assert conferma(db, iscrizione_id, admin_id) is S.CONFERMATA

    with Session(db) as sessione:
        assert sessione.get_one(Iscrizione, iscrizione_id).stato is S.CONFERMATA
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 1


def test_senza_posti_va_in_lista_d_attesa(db: Engine) -> None:
    edizione_id, [iscrizione_id], admin_id = prepara(
        db, capienza=2, posti_confermati=2, approvate=1
    )

    assert conferma(db, iscrizione_id, admin_id) is S.IN_ATTESA

    with Session(db) as sessione:
        assert sessione.get_one(Iscrizione, iscrizione_id).stato is S.IN_ATTESA
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 2


def test_r6_la_conferma_scrive_l_evento_di_audit(db: Engine) -> None:
    _, [iscrizione_id], admin_id = prepara(db, capienza=1, posti_confermati=0, approvate=1)

    conferma(db, iscrizione_id, admin_id)

    with Session(db) as sessione:
        [evento] = eventi_audit(sessione, iscrizione_id)
    assert (evento.stato_da, evento.stato_a, evento.autore_id) == (
        S.APPROVATA,
        S.CONFERMATA,
        admin_id,
    )
    assert evento.avvenuto_il is not None


@pytest.mark.parametrize("stato", [s for s in S if s is not S.APPROVATA])
def test_r7_conferma_solo_da_approvata(db: Engine, stato: StatoIscrizione) -> None:
    with Session(db) as sessione:
        admin = crea_persona(sessione, "Admin")
        edizione = crea_edizione(sessione, capienza=5, posti_confermati=1)
        iscrizione = crea_iscrizione(sessione, crea_persona(sessione, "Anna"), edizione, stato)
        sessione.commit()
        iscrizione_id, edizione_id, admin_id = iscrizione.id, edizione.id, admin.id

    with pytest.raises(TransizioneNonConsentita) as errore:
        conferma(db, iscrizione_id, admin_id)
    assert (errore.value.da, errore.value.a) == (stato, S.CONFERMATA)

    with Session(db) as sessione:
        assert sessione.get_one(Iscrizione, iscrizione_id).stato is stato
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 1
        assert eventi_audit(sessione, iscrizione_id) == []


def test_edizione_cancellata_non_si_conferma(db: Engine) -> None:
    edizione_id, [iscrizione_id], admin_id = prepara(
        db, capienza=2, posti_confermati=0, approvate=1
    )
    with Session(db) as sessione, sessione.begin():
        sessione.get_one(Edizione, edizione_id).cancellata_il = datetime.now(UTC)

    with pytest.raises(EdizioneCancellata):
        conferma(db, iscrizione_id, admin_id)

    with Session(db) as sessione:
        assert sessione.get_one(Iscrizione, iscrizione_id).stato is S.APPROVATA
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 0
        assert eventi_audit(sessione, iscrizione_id) == []


def test_iscrizione_inesistente(db: Engine) -> None:
    _, _, admin_id = prepara(db, capienza=1, posti_confermati=0, approvate=0)

    with pytest.raises(IscrizioneNonTrovata):
        conferma(db, 999, admin_id)


@pytest.mark.parametrize("concorrenti", [2, 10])
def test_r3_conferme_simultanee_sull_ultimo_posto_ne_passa_una_sola(
    db: Engine, concorrenti: int
) -> None:
    """Criterio di completamento della fase 4."""
    edizione_id, iscrizioni, admin_id = prepara(
        db, capienza=3, posti_confermati=2, approvate=concorrenti
    )
    via = threading.Barrier(concorrenti, timeout=30)

    def al_via(iscrizione_id: int) -> StatoIscrizione:
        with Session(db) as sessione, sessione.begin():
            # Connessione già aperta prima del via: altrimenti il tempo di connessione
            # distanzia i thread e la gara non avviene.
            sessione.connection()
            via.wait()
            return conferma_posto(sessione, iscrizione_id, admin_id)

    with ThreadPoolExecutor(max_workers=concorrenti) as esecutore:
        esiti = list(esecutore.map(al_via, iscrizioni))

    assert sorted(esiti) == sorted([S.CONFERMATA] + [S.IN_ATTESA] * (concorrenti - 1))
    with Session(db) as sessione:
        assert sessione.get_one(Edizione, edizione_id).posti_confermati == 3
        confermate = sessione.scalar(
            select(func.count()).where(
                Iscrizione.edizione_id == edizione_id, Iscrizione.stato == S.CONFERMATA
            )
        )
        assert confermate == 1
        for iscrizione_id in iscrizioni:
            assert len(eventi_audit(sessione, iscrizione_id)) == 1
