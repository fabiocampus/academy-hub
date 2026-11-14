"""Chiavi lette dal JWKS con il vero `PyJWKClient`, servito da un HTTP locale (ADR-0008)."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from academy_hub.api.identita import IdentitaNonDisponibile, Oidc, PerEmail, chiavi_da_jwks
from academy_hub.dominio.errori import NonAutenticato

from .oidc import EMITTENTE, PUBBLICO, ProviderFinto

DURATA_CACHE_S = 0.2


def _jwk(chiave: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(chiave.public_key()))
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


@dataclass
class Risposta:
    stato: int = 200
    corpo: bytes = b"{}"


class ServerJwks:
    def __init__(self) -> None:
        self.risposta = Risposta()
        risposta = self

        class Gestore(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(risposta.risposta.stato)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(risposta.risposta.corpo)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/certs"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def pubblica(self, *chiavi: tuple[rsa.RSAPrivateKey, str]) -> None:
        corpo = {"keys": [_jwk(chiave, kid) for chiave, kid in chiavi]}
        self.risposta = Risposta(200, json.dumps(corpo).encode())

    def chiudi(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def server() -> Iterator[ServerJwks]:
    server = ServerJwks()
    yield server
    server.chiudi()


@pytest.fixture(scope="module")
def provider() -> ProviderFinto:
    return ProviderFinto()


def _oidc(url: str) -> Oidc:
    return Oidc(EMITTENTE, PUBBLICO, chiavi_da_jwks(url, durata_cache_s=DURATA_CACHE_S))


def _bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def test_token_firmato_con_una_chiave_del_jwks(server: ServerJwks, provider: ProviderFinto) -> None:
    server.pubblica((provider.chiave, "chiave-di-test"))

    assert _oidc(server.url).identifica(_bearer(provider.token())) == PerEmail("anna@esempio.test")


def test_kid_assente_dal_jwks_401(server: ServerJwks, provider: ProviderFinto) -> None:
    server.pubblica((provider.chiave, "un-altro-kid"))

    with pytest.raises(NonAutenticato):
        _oidc(server.url).identifica(_bearer(provider.token()))


def test_token_senza_kid_401(server: ServerJwks, provider: ProviderFinto) -> None:
    server.pubblica((provider.chiave, "chiave-di-test"))
    token = jwt.encode(
        jwt.decode(provider.token(), options={"verify_signature": False}),
        provider.chiave,
        algorithm="RS256",
    )

    with pytest.raises(NonAutenticato):
        _oidc(server.url).identifica(_bearer(token))


def test_chiave_tolta_dal_jwks_smette_di_valere(
    server: ServerJwks, provider: ProviderFinto
) -> None:
    """Rotazione o revoca: dopo la durata della cache la chiave vecchia non vale più."""
    oidc = _oidc(server.url)
    server.pubblica((provider.chiave, "chiave-di-test"))
    assert isinstance(oidc.identifica(_bearer(provider.token())), PerEmail)

    nuova = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server.pubblica((nuova, "chiave-nuova"))
    time.sleep(DURATA_CACHE_S * 2)

    with pytest.raises(NonAutenticato):
        oidc.identifica(_bearer(provider.token()))
    assert isinstance(
        oidc.identifica(_bearer(provider.token(chiave=nuova, kid="chiave-nuova"))), PerEmail
    )


@pytest.mark.parametrize(
    "risposta",
    [
        pytest.param(Risposta(500, b'{"errore": "giu"}'), id="http-500"),
        pytest.param(Risposta(200, b"<html>proxy</html>"), id="non-json"),
        pytest.param(Risposta(200, b"[]"), id="non-un-oggetto"),
        pytest.param(Risposta(200, b'{"keys": []}'), id="senza-chiavi"),
        pytest.param(Risposta(200, b'{"keys": [{"kty": "RSA"}]}'), id="chiave-inutilizzabile"),
        pytest.param(Risposta(200, b'{"senza": "keys"}'), id="senza-campo-keys"),
    ],
)
def test_jwks_guasto_503(server: ServerJwks, provider: ProviderFinto, risposta: Risposta) -> None:
    server.risposta = risposta

    with pytest.raises(IdentitaNonDisponibile):
        _oidc(server.url).identifica(_bearer(provider.token()))


def test_jwks_irraggiungibile_503(provider: ProviderFinto) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    # Nessuno ascolta più su quella porta: connessione rifiutata.

    with pytest.raises(IdentitaNonDisponibile):
        _oidc(f"http://127.0.0.1:{porta}/certs").identifica(_bearer(provider.token()))
