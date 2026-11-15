"""Chi sono e come si accede (issue #59): le due rotte che il frontend chiama per prime.
Più l'elenco dei docenti per la gestione Academy (issue #64)."""

from fastapi import APIRouter

from academy_hub.api.dipendenze import AttoreCorrente, SessioneDb
from academy_hub.api.errori import risposte
from academy_hub.api.schemi import (
    ConfigurazioneClient,
    ConfigurazioneOidc,
    FlagFunzioni,
    PersonaInBreve,
    Profilo,
)
from academy_hub.config import Impostazioni, impostazioni
from academy_hub.servizi import persone

router = APIRouter(tags=["profilo"])


@router.get("/io", responses=risposte(401, 403), operation_id="chiSono")
def chi_sono(sessione: SessioneDb, attore: AttoreCorrente) -> Profilo:
    p = persone.profilo(sessione, attore)
    return Profilo(
        persona_id=p.persona_id,
        nome=p.nome,
        email=p.email,
        team_id=p.team_id,
        ruoli=sorted(p.ruoli),
        responsabile_di_team=p.responsabile_di_team,
    )


def configurazione_client(imp: Impostazioni) -> ConfigurazioneClient:
    """Solo dati pubblici: l'emittente e il client id stanno comunque nella pagina di login."""
    oidc = None
    if imp.identita == "oidc":
        oidc = ConfigurazioneOidc(emittente=imp.oidc_emittente, client_id=imp.oidc_client_web)
    return ConfigurazioneClient(
        identita=imp.identita, oidc=oidc, flag=FlagFunzioni(calendario=imp.flag_calendario)
    )


@router.get("/configurazione", operation_id="configurazione")
def configurazione() -> ConfigurazioneClient:
    """Pubblica: il frontend la legge prima di sapere chi è l'utente."""
    return configurazione_client(impostazioni())


@router.get(
    "/docenti", tags=["gestione"], responses=risposte(401, 403), operation_id="elencoDocenti"
)
def elenco_docenti(sessione: SessioneDb, attore: AttoreCorrente) -> list[PersonaInBreve]:
    """Le persone con il ruolo docente, per nome: chi può tenere un'edizione."""
    return [PersonaInBreve.model_validate(p) for p in persone.docenti(sessione, attore)]
