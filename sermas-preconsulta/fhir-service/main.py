"""
SERMAS Pre-Consulta — FHIR Service

Recibe el resumen de síntomas del voice-agent, cruza con el historial
del paciente (HSIC en producción, Synthea local en prototipo),
llama al llm-service para generar el triaje, y guarda el caso.

Endpoints:
  POST /fhir/preconsulta   — recibe síntomas del voice-agent
  GET  /fhir/casos         — lista casos pendientes (para el dashboard)
  GET  /health
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fhir_client import get_patient_bundle
from mapper import map_bundle
from notifier import notify_patient

app = FastAPI(title="SERMAS Pre-Consulta — FHIR Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_PATH = Path(__file__).parent.parent / "dashboard" / "index.html"

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")
CASES_FILE = Path(__file__).parent / "data" / "cases.json"
CASES_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Modelos ──────────────────────────────────────────────────────────────────

class PreConsultaRequest(BaseModel):
    session_id: str
    cip: str | None
    symptoms: dict
    caller_phone: str | None = None  # número del paciente (From de Twilio)


class CaseAction(BaseModel):
    action: str  # "call_now" | "keep_appointment" | "refer_emergency"


# ── Helpers de persistencia ──────────────────────────────────────────────────

def _load_cases() -> list:
    if not CASES_FILE.exists():
        return []
    with open(CASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_cases(cases: list) -> None:
    with open(CASES_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-service"}


@app.get("/")
async def dashboard():
    return FileResponse(DASHBOARD_PATH)


@app.post("/fhir/preconsulta")
async def create_preconsulta(payload: PreConsultaRequest):
    """
    Flujo principal:
    1. Buscar historial del paciente por CIP
    2. Mapear Bundle FHIR a dict limpio
    3. Llamar al llm-service para generar triaje
    4. Guardar caso en cases.json
    5. Devolver el caso creado
    """
    if not payload.cip:
        raise HTTPException(status_code=422, detail="CIP requerido")

    # 1. Historial FHIR
    bundle = await get_patient_bundle(payload.cip)
    if not bundle:
        # Paciente no encontrado — crear entrada mínima sin historial
        history = {"paciente": {"cip": payload.cip}, "diagnosticos_activos": [],
                   "medicacion_actual": [], "alergias": [], "visitas_recientes": []}
    else:
        history = map_bundle(bundle)

    # 2. Llamar al llm-service para triaje
    triage = await _call_llm_service(payload.symptoms, history)

    # 3. Construir y guardar caso
    case = {
        "id": str(uuid.uuid4()),
        "session_id": payload.session_id,
        "cip": payload.cip,
        "caller_phone": payload.caller_phone,
        "timestamp": datetime.now().isoformat(),
        "symptoms": payload.symptoms,
        "history": history,
        "triage": triage,
        "status": "pending",  # pending | call_now | keep_appointment | refer_emergency
        "notification": None,
    }

    cases = _load_cases()
    cases.append(case)
    _save_cases(cases)

    return case


@app.get("/fhir/casos")
async def get_cases():
    """Devuelve casos pendientes ordenados por urgencia (alta primero)."""
    cases = _load_cases()
    pending = [c for c in cases if c.get("status") == "pending"]

    urgency_order = {"alta": 0, "media": 1, "baja": 2}
    pending.sort(key=lambda c: urgency_order.get(
        c.get("triage", {}).get("urgencia", "baja"), 2
    ))

    return pending


@app.post("/fhir/casos/{case_id}/accion")
async def update_case_action(case_id: str, body: CaseAction):
    """El médico toma una decisión — actualiza el caso y notifica al paciente."""
    cases = _load_cases()
    for case in cases:
        if case["id"] == case_id:
            case["status"] = body.action
            case["actioned_at"] = datetime.now().isoformat()

            # Notificar al paciente
            patient_name = case.get("history", {}).get("paciente", {}).get("nombre", "paciente")
            phone = case.get("caller_phone")
            notification = await notify_patient(phone, body.action, patient_name)
            case["notification"] = notification

            _save_cases(cases)
            return case
    raise HTTPException(status_code=404, detail="Caso no encontrado")


# ── Llamada al llm-service ────────────────────────────────────────────────────

async def _call_llm_service(symptoms: dict, history: dict) -> dict:
    """
    Llama al llm-service para generar el triaje.
    Si no está disponible, devuelve un triaje de fallback.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{LLM_SERVICE_URL}/briefing/generate",
                json={"symptoms": symptoms, "history": history},
            )
            return r.json()
    except httpx.RequestError as exc:
        print(f"[WARN] llm-service no disponible: {exc}")
        return {
            "urgencia": "media",
            "resumen": "No se pudo generar triaje automático. Revisar manualmente.",
            "alertas": [],
            "recomendacion": "Contactar con el paciente para valoración directa.",
        }