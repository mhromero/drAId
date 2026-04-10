"""
SERMAS Pre-Consulta — FHIR Service (stub)

Recibe el resumen de síntomas del voice-agent, cruza con el historial
del paciente (datos sintéticos Synthea) y devuelve recursos FHIR.

TODO: implementar fhir_client.py con datos Synthea reales.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="SERMAS Pre-Consulta — FHIR Service", version="0.1.0")


class PreConsultaRequest(BaseModel):
    session_id: str
    cip: Optional[str]
    symptoms: dict


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-service"}


@app.post("/fhir/preconsulta")
async def create_preconsulta(payload: PreConsultaRequest):
    """
    1. Busca historial FHIR del paciente por CIP (Synthea en demo, SERMAS en prod)
    2. Combina síntomas recogidos + historial
    3. Llama al llm-service para generar el briefing
    4. Devuelve DocumentReference FHIR con el briefing

    TODO: implementar lógica completa en fhir_client.py
    """
    print(f"[fhir-service] Recibido session={payload.session_id} CIP={payload.cip}")

    # Stub: devolver estructura FHIR mínima
    return {
        "resourceType": "DocumentReference",
        "status": "current",
        "subject": {"identifier": {"value": payload.cip}},
        "description": "Pre-consulta pendiente de procesamiento",
        "content": [{"attachment": {"data": payload.symptoms}}],
    }