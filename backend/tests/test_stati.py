"""Transizioni dell'iscrizione (R7): la tabella di CONTEXT.md è la specifica."""

import itertools

import pytest

from academy_hub.dominio.stati import (
    StatoIscrizione,
    TransizioneNonConsentita,
    verifica_transizione,
)

S = StatoIscrizione

# Copiata a mano dalla tabella «Stati dell'iscrizione» di CONTEXT.md.
CONSENTITE = {
    (S.RICHIESTA, S.APPROVATA),
    (S.RICHIESTA, S.RIFIUTATA),
    (S.APPROVATA, S.CONFERMATA),
    (S.APPROVATA, S.IN_ATTESA),
    (S.IN_ATTESA, S.CONFERMATA),
    (S.RICHIESTA, S.ANNULLATA),
    (S.APPROVATA, S.ANNULLATA),
    (S.IN_ATTESA, S.ANNULLATA),
    (S.CONFERMATA, S.ANNULLATA),
    (S.CONFERMATA, S.COMPLETATA),
}


def test_i_valori_sono_quelli_del_glossario() -> None:
    assert [s.value for s in S] == [
        "Richiesta",
        "Approvata",
        "Rifiutata",
        "InAttesa",
        "Confermata",
        "Annullata",
        "Completata",
    ]


@pytest.mark.parametrize(("da", "a"), sorted(CONSENTITE))
def test_transizione_consentita(da: StatoIscrizione, a: StatoIscrizione) -> None:
    verifica_transizione(da, a)


@pytest.mark.parametrize(
    ("da", "a"),
    sorted(set(itertools.product(S, S)) - CONSENTITE),
)
def test_ogni_altra_transizione_e_rifiutata(da: StatoIscrizione, a: StatoIscrizione) -> None:
    with pytest.raises(TransizioneNonConsentita) as errore:
        verifica_transizione(da, a)
    assert errore.value.da is da
    assert errore.value.a is a
    assert f"{da.value} → {a.value}" in str(errore.value)


def test_stati_attivi() -> None:
    attivi = {s for s in S if s.attivo}
    assert attivi == {S.RICHIESTA, S.APPROVATA, S.IN_ATTESA, S.CONFERMATA}
