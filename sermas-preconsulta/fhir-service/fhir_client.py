"""
FHIR Client — carga el historial clínico de un paciente por CIP.

PROTOTIPO: lee ficheros JSON locales generados por generate_patients.py
PRODUCCIÓN (HSIC/ORUS): descomentar el bloque FHIR server y configurar
    FHIR_MODE=fhir + FHIR_SERVER_URL en .env

La firma de get_patient_bundle() no cambia entre modos.
"""

import json
import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCCIÓN: cliente FHIR R4 contra HSIC/ORUS
# Requiere: FHIR_SERVER_URL, FHIR_CLIENT_ID, FHIR_CLIENT_SECRET (OAuth2)
# ─────────────────────────────────────────────────────────────────────────────
# import httpx
#
# async def get_patient_bundle(cip: str) -> dict | None:
#     server = os.getenv("FHIR_SERVER_URL")
#     token = await _get_oauth_token()
#     headers = {"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"}
#
#     async with httpx.AsyncClient() as client:
#         # 1. Buscar paciente por CIP
#         r = await client.get(f"{server}/Patient?identifier={cip}", headers=headers)
#         patients = r.json().get("entry", [])
#         if not patients:
#             return None
#         pid = patients[0]["resource"]["id"]
#
#         # 2. Fetch recursos clínicos
#         resources = []
#         for resource_type in ["Condition", "MedicationRequest", "AllergyIntolerance", "Encounter"]:
#             r = await client.get(f"{server}/{resource_type}?patient={pid}&_count=20", headers=headers)
#             resources += r.json().get("entry", [])
#
#     return {"resourceType": "Bundle", "type": "collection",
#             "entry": [{"resource": patients[0]["resource"]}] + resources}
#
# async def _get_oauth_token() -> str:
#     """OAuth2 client credentials contra el IdP del SERMAS."""
#     async with httpx.AsyncClient() as client:
#         r = await client.post(
#             os.getenv("FHIR_TOKEN_URL"),
#             data={"grant_type": "client_credentials",
#                   "client_id": os.getenv("FHIR_CLIENT_ID"),
#                   "client_secret": os.getenv("FHIR_CLIENT_SECRET")},
#         )
#     return r.json()["access_token"]
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# PROTOTIPO: lectura de ficheros locales (data/patients/{CIP}.json)
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data" / "patients"


async def get_patient_bundle(cip: str) -> dict | None:
    """Devuelve el Bundle FHIR del paciente o None si no existe."""
    path = DATA_DIR / f"{cip}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)