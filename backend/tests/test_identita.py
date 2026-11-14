"""Provider d'identità (ADR-0008), senza database: chi è la persona, mai i suoi ruoli."""

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from academy_hub.api.identita import (
    Databricks,
    IdentitaNonDisponibile,
    Oidc,
    PerEmail,
    PerId,
    Provvisoria,
)
from academy_hub.dominio.errori import NonAutenticato

from .oidc import EMITTENTE, PUBBLICO, ProviderFinto


@pytest.fixture(scope="module")
def provider() -> ProviderFinto:
    return ProviderFinto()


def _bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def test_token_valido_identifica_per_email(provider: ProviderFinto) -> None:
    assert provider.oidc().identifica(_bearer(provider.token("anna@esempio.test"))) == PerEmail(
        "anna@esempio.test"
    )


def test_email_del_token_portata_in_minuscolo(provider: ProviderFinto) -> None:
    identita = provider.oidc().identifica(_bearer(provider.token("Anna@Esempio.TEST")))

    assert identita == PerEmail("anna@esempio.test")


def test_schema_bearer_senza_distinzione_di_maiuscole(provider: ProviderFinto) -> None:
    intestazioni = {"authorization": f"bearer {provider.token()}"}

    assert isinstance(provider.oidc().identifica(intestazioni), PerEmail)


@pytest.mark.parametrize(
    ("authorization", "motivo"),
    [
        (None, "mancante"),
        ("", "Bearer"),
        ("Bearer", "Bearer"),
        ("Bearer   ", "Bearer"),
        ("Basic YW5uYTpwYXNzd29yZA==", "Bearer"),
        ("Bearer non.un.jwt", "non valido"),
    ],
)
def test_authorization_assente_o_malformata(
    provider: ProviderFinto, authorization: str | None, motivo: str
) -> None:
    intestazioni = {} if authorization is None else {"authorization": authorization}

    with pytest.raises(NonAutenticato, match=motivo):
        provider.oidc().identifica(intestazioni)


@pytest.mark.parametrize(
    "rivendicazioni",
    [
        pytest.param({"exp": int(time.time()) - 120}, id="scaduto"),
        pytest.param({"aud": "un-altro-servizio"}, id="pubblico-diverso"),
        pytest.param({"iss": "http://altro.test/realms/academy"}, id="emittente-diverso"),
        pytest.param({"exp": None}, id="senza-scadenza"),
        pytest.param({"aud": None}, id="senza-pubblico"),
        pytest.param({"iat": None}, id="senza-emissione"),
        pytest.param({"email_verified": False}, id="email-non-verificata"),
        pytest.param({"email_verified": None}, id="email-verified-assente"),
        pytest.param({"email_verified": "true"}, id="email-verified-stringa"),
    ],
)
def test_token_rifiutato(provider: ProviderFinto, rivendicazioni: dict[str, Any]) -> None:
    with pytest.raises(NonAutenticato):
        provider.oidc().identifica(_bearer(provider.token(**rivendicazioni)))


@pytest.mark.parametrize("email", [None, "", "senza-chiocciola", "a@b@c", "spazi @x.test", 42])
def test_email_mancante_o_non_valida(provider: ProviderFinto, email: object) -> None:
    altro: dict[str, Any] = {} if email is None else {"email": email}
    token = provider.token(None, **altro)

    with pytest.raises(NonAutenticato, match="Email"):
        provider.oidc().identifica(_bearer(token))


def test_scaduto_da_poco_accettato_entro_la_tolleranza(provider: ProviderFinto) -> None:
    token = provider.token(exp=int(time.time()) - 10)

    assert isinstance(provider.oidc().identifica(_bearer(token)), PerEmail)


def test_firmato_da_un_altra_chiave(provider: ProviderFinto) -> None:
    estranea = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(NonAutenticato, match="non valido"):
        provider.oidc().identifica(_bearer(provider.token(chiave=estranea)))


def test_kid_sconosciuto(provider: ProviderFinto) -> None:
    with pytest.raises(NonAutenticato):
        provider.oidc().identifica(_bearer(provider.token(kid="ruotata")))


def _token_non_firmato() -> str:
    dati = {
        "iss": EMITTENTE,
        "aud": PUBBLICO,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "email": "anna@esempio.test",
        "email_verified": True,
    }
    return jwt.encode(dati, "", algorithm="none", headers={"kid": "chiave-di-test"})


def test_algoritmo_none_rifiutato(provider: ProviderFinto) -> None:
    with pytest.raises(NonAutenticato):
        provider.oidc().identifica(_bearer(_token_non_firmato()))


def test_algoritmo_simmetrico_rifiutato(provider: ProviderFinto) -> None:
    """Confusione di algoritmi: HS256 firmato con la chiave pubblica usata come segreto."""
    dati = jwt.decode(_token_non_firmato(), options={"verify_signature": False})
    token = jwt.encode(
        dati,
        "segreto-qualunque-lungo-abbastanza-32b",
        algorithm="HS256",
        headers={"kid": "chiave-di-test"},
    )

    with pytest.raises(NonAutenticato):
        provider.oidc().identifica(_bearer(token))


def test_chiavi_irraggiungibili_non_e_un_401(provider: ProviderFinto) -> None:
    """Se il JWKS non risponde non si sa se il token è valido: errore del servizio (503)."""

    def giu(_token: str) -> Any:
        raise jwt.PyJWKClientConnectionError("connessione rifiutata")

    oidc = Oidc(EMITTENTE, PUBBLICO, giu)

    with pytest.raises(IdentitaNonDisponibile):
        oidc.identifica(_bearer(provider.token()))


def test_databricks_legge_x_forwarded_email() -> None:
    identita = Databricks().identifica({"x-forwarded-email": "Bruno@Esempio.test"})

    assert identita == PerEmail("bruno@esempio.test")


def test_databricks_senza_header() -> None:
    with pytest.raises(NonAutenticato, match="X-Forwarded-Email"):
        Databricks().identifica({"authorization": "Bearer qualcosa"})


def test_databricks_ignora_x_persona_id() -> None:
    with pytest.raises(NonAutenticato):
        Databricks().identifica({"x-persona-id": "1"})


def test_provvisoria_legge_x_persona_id() -> None:
    assert Provvisoria().identifica({"x-persona-id": "7"}) == PerId(7)


def test_provvisoria_ignora_il_token(provider: ProviderFinto) -> None:
    with pytest.raises(NonAutenticato):
        Provvisoria().identifica(_bearer(provider.token()))
