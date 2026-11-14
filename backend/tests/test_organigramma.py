"""Responsabile diretto (R2, D7, D9): regola pura, senza database."""

import pytest

from academy_hub.dominio.attore import Attore
from academy_hub.dominio.errori import AzioneNonConsentita
from academy_hub.dominio.organigramma import (
    AMMINISTRAZIONE,
    AutoApprovazione,
    NonResponsabileDiretto,
    responsabile_diretto,
    verifica_decisore,
)
from academy_hub.dominio.ruoli import Ruolo

# Catena: responsabili dal team del richiedente fino al vertice (None = team senza responsabile).
DIPENDENTE, RESP_TEAM, RESP_PADRE, ADMIN = 1, 2, 3, 4


def attore(persona_id: int, *ruoli: Ruolo) -> Attore:
    return Attore(persona_id, team_id=1, ruoli=frozenset(ruoli or (Ruolo.DIPENDENTE,)))


@pytest.mark.parametrize(
    ("richiedente", "catena", "atteso"),
    [
        # Dipendente: il responsabile del suo team.
        (DIPENDENTE, (RESP_TEAM, RESP_PADRE), RESP_TEAM),
        # D7: un responsabile sale al team padre.
        (RESP_TEAM, (RESP_TEAM, RESP_PADRE), RESP_PADRE),
        # D7: il responsabile del team al vertice va all'amministrazione Academy.
        (RESP_PADRE, (RESP_PADRE,), AMMINISTRAZIONE),
        # Team senza responsabile: si sale finché se ne trova uno.
        (DIPENDENTE, (None, RESP_PADRE), RESP_PADRE),
        (DIPENDENTE, (None,), AMMINISTRAZIONE),
        # Stessa persona responsabile di due team annidati: non approva se stessa.
        (RESP_TEAM, (RESP_TEAM, RESP_TEAM, RESP_PADRE), RESP_PADRE),
    ],
)
def test_responsabile_diretto(
    richiedente: int, catena: tuple[int | None, ...], atteso: object
) -> None:
    assert responsabile_diretto(richiedente, catena) == atteso


def test_il_responsabile_diretto_decide() -> None:
    verifica_decisore(attore(RESP_TEAM, Ruolo.RESPONSABILE), DIPENDENTE, (RESP_TEAM, RESP_PADRE))


def test_r2_un_altro_responsabile_non_decide() -> None:
    with pytest.raises(NonResponsabileDiretto):
        verifica_decisore(
            attore(RESP_PADRE, Ruolo.RESPONSABILE), DIPENDENTE, (RESP_TEAM, RESP_PADRE)
        )


def test_r2_nessuno_decide_sulle_proprie_richieste() -> None:
    # Anche un amministratore, anche quando la richiesta toccherebbe all'amministrazione.
    with pytest.raises(AutoApprovazione):
        verifica_decisore(attore(ADMIN, Ruolo.ADMIN_ACADEMY), ADMIN, (ADMIN,))


def test_d7_al_vertice_decide_l_amministratore_academy() -> None:
    verifica_decisore(attore(ADMIN, Ruolo.ADMIN_ACADEMY), RESP_PADRE, (RESP_PADRE,))


def test_d7_al_vertice_un_dipendente_non_decide() -> None:
    with pytest.raises(NonResponsabileDiretto):
        verifica_decisore(attore(DIPENDENTE), RESP_PADRE, (RESP_PADRE,))


def test_l_amministratore_non_scavalca_il_responsabile() -> None:
    with pytest.raises(NonResponsabileDiretto):
        verifica_decisore(attore(ADMIN, Ruolo.ADMIN_ACADEMY), DIPENDENTE, (RESP_TEAM,))


def test_gli_errori_sono_403() -> None:
    assert issubclass(NonResponsabileDiretto, AzioneNonConsentita)
    assert issubclass(AutoApprovazione, AzioneNonConsentita)
