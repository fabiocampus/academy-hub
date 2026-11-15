"""Gli schemi che il bundle nomina esistono: li crea Terraform (post-mortem 2026-11-15).

Il bundle (`databricks.yml`) passa ai task e alla pipeline nomi come
``${var.catalogo}.gold``; gli schemi li crea `infra/databricks/unity_catalog.tf` (ADR-0012).
Nessuno dei due lo controlla al deploy: uno schema sbagliato fa fallire il job solo quando
gira.
"""

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]


def schemi_di_terraform() -> set[str]:
    testo = (RADICE / "infra" / "databricks" / "unity_catalog.tf").read_text(encoding="utf-8")
    blocco = re.search(r"livelli = \{(.*?)\n  \}", testo, re.DOTALL)
    assert blocco is not None, "blocco `livelli` non trovato in unity_catalog.tf"
    return set(re.findall(r"^\s+(\w+)\s+=", blocco.group(1), re.MULTILINE))


def schemi_del_bundle() -> set[str]:
    testo = (RADICE / "databricks.yml").read_text(encoding="utf-8")
    return set(re.findall(r"\$\{var\.catalogo\}[./](\w+)", testo))


def test_terraform_crea_gli_schemi_attesi() -> None:
    assert {"bronze", "silver", "gold", "qualita"} <= schemi_di_terraform()


def test_ogni_schema_nominato_dal_bundle_esiste() -> None:
    nominati = schemi_del_bundle()

    assert nominati, "nessun ${var.catalogo}.<schema> trovato in databricks.yml"
    assert nominati <= schemi_di_terraform(), nominati - schemi_di_terraform()
