"""Un provider OIDC finto per i test: chiave RSA generata al volo e token firmati con essa."""

import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from academy_hub.api.identita import Oidc

EMITTENTE = "http://keycloak.test/realms/academy"
PUBBLICO = "academy-api"
KID = "chiave-di-test"


def _chiave() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class ProviderFinto:
    """Firma token come Keycloak; `oidc()` è il verificatore dell'app che si fida di lui."""

    chiave: rsa.RSAPrivateKey = field(default_factory=_chiave)

    def oidc(self) -> Oidc:
        pubblica = self.chiave.public_key()

        def trova_chiave(token: str) -> Any:
            if jwt.get_unverified_header(token).get("kid") != KID:
                raise jwt.PyJWKClientError("kid sconosciuto")
            return pubblica

        return Oidc(EMITTENTE, PUBBLICO, trova_chiave)

    def token(
        self,
        email: str | None = "anna@esempio.test",
        /,
        *,
        chiave: rsa.RSAPrivateKey | None = None,
        kid: str = KID,
        **rivendicazioni: Any,
    ) -> str:
        adesso = int(time.time())
        dati: dict[str, Any] = {
            "iss": EMITTENTE,
            "aud": PUBBLICO,
            "sub": "soggetto-di-test",
            "iat": adesso,
            "exp": adesso + 300,
            "email_verified": True,
        }
        if email is not None:
            dati["email"] = email
        dati.update(rivendicazioni)  # anche "email", per provare valori non stringa
        dati = {k: v for k, v in dati.items() if v is not None}
        return jwt.encode(dati, chiave or self.chiave, algorithm="RS256", headers={"kid": kid})

    def intestazioni(self, email: str | None = "anna@esempio.test", **altro: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(email, **altro)}"}
