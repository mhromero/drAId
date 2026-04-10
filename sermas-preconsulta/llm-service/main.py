"""
SERMAS Pre-Consulta — LLM Service (stub)

Recibe síntomas + historial FHIR y genera el briefing pre-consulta
para el médico usando GPT-4o.

TODO: implementar briefing.py con el prompt clínico completo.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SERMAS Pre-Consulta — LLM Service", version="0.1.0")


class BriefingRequest(BaseModel):
    session_id: str
    symptoms: dict
    fhir_history: dict  # Recursos FHIR del paciente


@app.get("/health")
async def health():
    return {"status": "ok", "service": "llm-service"}


@app.post("/briefing/generate")
async def generate_briefing(payload: BriefingRequest):
    """
    Genera un briefing clínico estructurado para el médico.
    TODO: implementar en briefing.py
    """
    return {
        "session_id": payload.session_id,
        "briefing": "Briefing pendiente de generación (stub)",
    }