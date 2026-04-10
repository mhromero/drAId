"""
SERMAS Pre-Consulta — LLM Service

Recibe síntomas + historial FHIR mapeado y genera un triaje clínico
estructurado para el médico.

Endpoints:
  POST /briefing/generate  — genera triaje
  GET  /health
"""

from fastapi import FastAPI
from pydantic import BaseModel
from triage import generate_triage

app = FastAPI(title="SERMAS Pre-Consulta — LLM Service", version="0.1.0")


class BriefingRequest(BaseModel):
    symptoms: dict
    history: dict


@app.get("/health")
async def health():
    return {"status": "ok", "service": "llm-service"}


@app.post("/briefing/generate")
async def generate_briefing(payload: BriefingRequest):
    return await generate_triage(payload.symptoms, payload.history)