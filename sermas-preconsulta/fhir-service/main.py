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
import base64
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, RedirectResponse
from pydantic import BaseModel

from fhir_client import get_patient_bundle
from hcis_master import build_patient_master_record, to_legacy_history_view
from mapper import map_bundle
from notifier import notify_patient

app = FastAPI(title="SERMAS Pre-Consulta — FHIR Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
DASHBOARD_PATH = DASHBOARD_DIR / "index.html"
PATIENT_HISTORY_PATH = DASHBOARD_DIR / "historial.html"

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8002")
SEARCH_SERVICE_URL = os.getenv("SEARCH_SERVICE_URL")
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


def _get_cached_history_for_cip(cip: str) -> dict | None:
    """
    Recupera el historial más reciente guardado en cases.json para un CIP.
    Se usa como fallback cuando no hay bundle FHIR local/remoto disponible.
    """
    for case in reversed(_load_cases()):
        if case.get("cip") == cip and case.get("history"):
            return case["history"]
    return None


def _to_hcis_structure_from_bundle(bundle: dict, cip: str) -> dict:
    """
    Convierte un Bundle FHIR a una estructura cercana a HCIS:
    paciente, problemas, tratamiento, alergias y episodios.
    """
    patient = {}
    problems = []
    medications = []
    allergies = []
    encounters = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")

        if rtype == "Patient":
            identifier = next(
                (i.get("value") for i in resource.get("identifier", [])
                 if "sermas" in (i.get("system") or "").lower()),
                None,
            )
            name = resource.get("name", [{}])[0]
            given = " ".join(name.get("given", []))
            family = name.get("family", "")
            patient = {
                "nombre_completo": f"{given} {family}".strip(),
                "cip": identifier or cip,
                "fecha_nacimiento": resource.get("birthDate"),
                "sexo": resource.get("gender"),
                "direccion": (resource.get("address") or [{}])[0],
            }

        elif rtype == "Condition":
            coding = (resource.get("code", {}).get("coding") or [{}])[0]
            clinical = ((resource.get("clinicalStatus") or {}).get("coding") or [{}])[0]
            problems.append({
                "estado": clinical.get("code"),
                "fecha_inicio": resource.get("onsetDateTime", "")[:10] if resource.get("onsetDateTime") else None,
                "codigo": coding.get("code"),
                "sistema_codigo": coding.get("system"),
                "descripcion": coding.get("display"),
            })

        elif rtype == "MedicationRequest":
            coding = (resource.get("medicationCodeableConcept", {}).get("coding") or [{}])[0]
            dosage = (resource.get("dosageInstruction") or [{}])[0]
            medications.append({
                "estado": resource.get("status"),
                "medicamento": coding.get("display"),
                "codigo": coding.get("code"),
                "sistema_codigo": coding.get("system"),
                "posologia": dosage.get("text"),
            })

        elif rtype == "AllergyIntolerance":
            coding = (resource.get("code", {}).get("coding") or [{}])[0]
            reaction = (resource.get("reaction") or [{}])[0]
            manifestation = (reaction.get("manifestation") or [{}])[0]
            mcoding = (manifestation.get("coding") or [{}])[0]
            allergies.append({
                "criticidad": resource.get("criticality"),
                "sustancia": coding.get("display"),
                "codigo": coding.get("code"),
                "sistema_codigo": coding.get("system"),
                "manifestacion": mcoding.get("display"),
            })

        elif rtype == "Encounter":
            reason = (resource.get("reasonCode") or [{}])[0]
            diagnosis = (resource.get("diagnosis") or [{}])[0].get("condition", {})
            encounters.append({
                "estado": resource.get("status"),
                "fecha": (resource.get("period") or {}).get("start", "")[:10] if (resource.get("period") or {}).get("start") else None,
                "motivo": reason.get("text"),
                "resultado": diagnosis.get("display"),
            })

    encounters.sort(key=lambda e: e.get("fecha") or "", reverse=True)

    return {
        "estructura": "HCIS",
        "paciente": patient or {"cip": cip},
        "problemas": problems,
        "tratamiento": medications,
        "alergias": allergies,
        "episodios": encounters,
    }


def _normalize_section_name(resource_type: str, resource: dict) -> str:
    if resource_type == "Condition":
        return "problemas_diagnosticos"
    if resource_type == "MedicationRequest":
        return "medicacion"
    if resource_type == "AllergyIntolerance":
        return "alergias_ram"
    if resource_type == "Encounter":
        reason = ((resource.get("reasonCode") or [{}])[0] or {}).get("text", "").lower()
        service = ((resource.get("serviceType") or {}).get("text") or "").lower()
        cls = ((resource.get("class") or {}).get("code") or "").lower()
        full = f"{reason} {service} {cls}"
        if any(x in full for x in ["urgenc", "emergenc", "er", "ed"]):
            return "urgencias"
        if any(x in full for x in ["hospitaliz", "inpatient", "imp", "ward"]):
            return "hospitalizacion"
        if any(x in full for x in ["consulta externa", "outpatient", "ambulator"]):
            return "consultas_externas"
        return "episodios_asistenciales"
    if resource_type == "DiagnosticReport":
        category = ((resource.get("category") or [{}])[0] or {}).get("text", "").lower()
        if any(x in category for x in ["radiolog", "imagen"]):
            return "pruebas_imagen"
        if any(x in category for x in ["laboratorio", "lab"]):
            return "laboratorio"
        return "informes_pruebas"
    if resource_type == "Observation":
        category = ((resource.get("category") or [{}])[0] or {}).get("text", "").lower()
        if any(x in category for x in ["vital", "constante"]):
            return "constantes_signos_vitales"
        if any(x in category for x in ["laboratorio", "lab"]):
            return "laboratorio"
        return "pruebas_observaciones"
    if resource_type == "DocumentReference":
        return "informes_documentos"
    if resource_type == "CarePlan":
        return "planes_cuidados"
    if resource_type == "Procedure":
        return "procedimientos"
    if resource_type == "ClinicalImpression":
        return "valoraciones_clinicas"
    if resource_type == "ServiceRequest":
        return "solicitudes_pruebas"
    if resource_type == "Immunization":
        return "vacunacion"
    if resource_type == "CareTeam":
        return "equipo_asistencial"
    if resource_type == "Composition":
        return "informes_alta_evolucion"
    return f"seccion_{resource_type.lower()}"


def _extract_timestamp(resource: dict) -> str | None:
    for key in [
        "recordedDate",
        "authoredOn",
        "date",
        "issued",
        "effectiveDateTime",
        "onsetDateTime",
    ]:
        value = resource.get(key)
        if isinstance(value, str) and value:
            return value[:19]
    period = resource.get("period") or {}
    if isinstance(period.get("start"), str):
        return period["start"][:19]
    return None


def _extract_author(resource: dict) -> str | None:
    recorder = resource.get("recorder") or {}
    if isinstance(recorder.get("display"), str) and recorder.get("display"):
        return recorder["display"]
    for key in ["asserter", "requester", "performer", "participant"]:
        value = resource.get(key)
        if isinstance(value, dict) and value.get("display"):
            return value["display"]
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                actor = first.get("actor") or first.get("individual") or first
                if isinstance(actor, dict) and actor.get("display"):
                    return actor["display"]
    return "No informado"


def _collect_texts(value, output: list[str]) -> None:
    if isinstance(value, str):
        v = value.strip()
        if len(v) >= 4:
            output.append(v)
    elif isinstance(value, list):
        for x in value:
            _collect_texts(x, output)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in {"id", "reference", "system", "url", "code", "resourceType", "data"}:
                continue
            _collect_texts(v, output)


def _hcis_section_catalog() -> list[dict]:
    """
    Catálogo funcional de apartados HCIS que intentamos leer.
    """
    return [
        {"section": "datos_paciente", "resources": ["Patient"]},
        {"section": "problemas_diagnosticos", "resources": ["Condition", "ClinicalImpression"]},
        {"section": "antecedentes_personales_familiares", "resources": ["Condition", "FamilyMemberHistory"]},
        {"section": "medicacion", "resources": ["MedicationRequest"]},
        {"section": "alergias_ram", "resources": ["AllergyIntolerance"]},
        {"section": "episodios_asistenciales", "resources": ["Encounter"]},
        {"section": "urgencias", "resources": ["Encounter"]},
        {"section": "hospitalizacion", "resources": ["Encounter"]},
        {"section": "consultas_externas", "resources": ["Encounter"]},
        {"section": "informes_alta_evolucion", "resources": ["Composition", "DocumentReference"]},
        {"section": "informes_pruebas", "resources": ["DiagnosticReport", "DocumentReference"]},
        {"section": "pruebas_observaciones", "resources": ["Observation"]},
        {"section": "laboratorio", "resources": ["DiagnosticReport", "Observation"]},
        {"section": "pruebas_imagen", "resources": ["DiagnosticReport", "DocumentReference"]},
        {"section": "procedimientos", "resources": ["Procedure"]},
        {"section": "planes_cuidados", "resources": ["CarePlan"]},
        {"section": "interconsultas", "resources": ["ServiceRequest", "Task"]},
        {"section": "solicitudes_pruebas", "resources": ["ServiceRequest"]},
        {"section": "vacunacion", "resources": ["Immunization"]},
        {"section": "equipo_asistencial", "resources": ["CareTeam"]},
        {"section": "anotaciones_notas_libres", "resources": ["DocumentReference", "Observation"]},
        {"section": "documentos_registros_transacciones", "resources": ["DocumentReference", "Provenance"]},
    ]


def _extract_document_reference_fragments(cip: str, resource: dict, doc_index: int) -> list[dict]:
    fragments = []
    timestamp = _extract_timestamp(resource) or "Sin fecha"
    author = _extract_author(resource) or "No informado"
    contents = resource.get("content") or []
    for content_index, content in enumerate(contents):
        attachment = content.get("attachment") or {}
        ctype = (attachment.get("contentType") or "application/octet-stream").lower()
        title = attachment.get("title") or f"Documento {doc_index + 1}"
        created = attachment.get("creation") or timestamp
        access_url = f"/fhir/pacientes/{cip}/documentos/{doc_index}/{content_index}"

        text = None
        data_b64 = attachment.get("data")
        if isinstance(data_b64, str) and data_b64:
            try:
                raw = base64.b64decode(data_b64, validate=False)
                if ctype.startswith("text/") or ctype in {"application/json", "application/xml"}:
                    text = raw.decode("utf-8", errors="replace")[:300]
            except Exception:
                text = None

        if not text:
            if "pdf" in ctype:
                text = f"{title} (PDF adjunto)"
            else:
                text = f"{title} ({ctype})"

        confidence = 0.92 if data_b64 else 0.8
        fragments.append({
            "source_section": "informes_documentos",
            "resource_type": "DocumentReference",
            "timestamp": (created or "Sin fecha")[:19],
            "author": author,
            "text": text,
            "confidence": round(confidence, 2),
            "manual_review": False,
            "document_access": {
                "content_type": ctype,
                "title": title,
                "url": access_url,
            },
        })
    return fragments


def _build_fragments_from_bundle(bundle: dict, cip: str) -> list[dict]:
    """
    Agregador HCIS all-sections:
    construye fragmentos trazables de TODAS las secciones del bundle.
    """
    fragments = []
    for entry_index, entry in enumerate(bundle.get("entry", [])):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "Unknown")
        section = _normalize_section_name(rtype, resource)
        timestamp = _extract_timestamp(resource) or "Sin fecha"
        author = _extract_author(resource) or "No informado"

        if rtype == "DocumentReference":
            fragments.extend(_extract_document_reference_fragments(cip, resource, entry_index))

        texts: list[str] = []
        _collect_texts(resource, texts)
        unique_texts = []
        seen = set()
        for t in texts:
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            unique_texts.append(t)

        chunk_size = 2 if len(unique_texts) > 5 else 1
        for i in range(0, len(unique_texts), chunk_size):
            chunk = " | ".join(unique_texts[i:i + chunk_size])[:450]
            if not chunk:
                continue
            confidence = 0.9 if timestamp != "Sin fecha" and author != "No informado" else 0.65
            fragment = {
                "source_section": section,
                "resource_type": rtype,
                "timestamp": timestamp,
                "author": author,
                "text": chunk,
                "confidence": round(confidence, 2),
                "manual_review": confidence < 0.75,
            }
            fragments.append(fragment)
    fragments.sort(key=lambda f: (f.get("timestamp") or ""), reverse=True)
    return fragments


async def _resolve_hcis_history(cip: str) -> dict | None:
    bundle = await get_patient_bundle(cip)
    if bundle:
        master_record = build_patient_master_record(bundle, cip)
        base = to_legacy_history_view(master_record, cip)
        if not base.get("all_sections"):
            # Fallback defensivo para no romper el dashboard si faltan secciones.
            base["all_sections"] = _build_fragments_from_bundle(bundle, cip)
        if not base.get("catalogo_hcis"):
            base["catalogo_hcis"] = _hcis_section_catalog()
        return base

    cached_history = _get_cached_history_for_cip(cip)
    if not cached_history:
        return None

    fallback = {
        "estructura": "HCIS",
        "paciente": cached_history.get("paciente", {"cip": cip}),
        "problemas": cached_history.get("diagnosticos_activos", []),
        "tratamiento": cached_history.get("medicacion_actual", []),
        "alergias": cached_history.get("alergias", []),
        "episodios": cached_history.get("visitas_recientes", []),
        "catalogo_hcis": _hcis_section_catalog(),
    }
    # Fallback all-sections cuando no hay bundle completo.
    fallback["all_sections"] = []
    for p in fallback["problemas"]:
        fallback["all_sections"].append({
            "source_section": "problemas_diagnosticos",
            "resource_type": "Condition",
            "timestamp": p.get("desde") or "Sin fecha",
            "author": "No informado",
            "text": f"{p.get('nombre', 'Problema')} | codigo {p.get('codigo_snomed', 's/d')}",
            "confidence": 0.6,
            "manual_review": True,
        })
    for m in fallback["tratamiento"]:
        fallback["all_sections"].append({
            "source_section": "medicacion",
            "resource_type": "MedicationRequest",
            "timestamp": "Sin fecha",
            "author": "No informado",
            "text": f"{m.get('nombre', 'Medicacion')} | {m.get('posologia', 'sin posologia')}",
            "confidence": 0.55,
            "manual_review": True,
        })
    for a in fallback["alergias"]:
        fallback["all_sections"].append({
            "source_section": "alergias_ram",
            "resource_type": "AllergyIntolerance",
            "timestamp": "Sin fecha",
            "author": "No informado",
            "text": f"{a.get('sustancia', 'Alergia')} | {a.get('manifestacion', 'sin manifestacion')}",
            "confidence": 0.55,
            "manual_review": True,
        })
    for e in fallback["episodios"]:
        fallback["all_sections"].append({
            "source_section": "episodios_asistenciales",
            "resource_type": "Encounter",
            "timestamp": e.get("fecha") or "Sin fecha",
            "author": "No informado",
            "text": f"{e.get('motivo', 'Motivo no disponible')} | {e.get('resultado', 'sin resultado')}",
            "confidence": 0.6,
            "manual_review": True,
        })
    return fallback


def _history_to_free_text(history: dict) -> str:
    p = history.get("paciente", {})
    lines = [
        "HISTORIAL CLINICO (FORMATO HCIS)",
        "",
        "DATOS DEL PACIENTE",
        f"- Nombre: {p.get('nombre_completo') or p.get('nombre') or 'No disponible'}",
        f"- CIP: {p.get('cip') or 'No disponible'}",
        f"- Fecha de nacimiento: {p.get('fecha_nacimiento') or 'No disponible'}",
        f"- Sexo: {p.get('sexo') or 'No disponible'}",
        "",
        "PROBLEMAS / DIAGNOSTICOS",
    ]

    problems = history.get("problemas", [])
    if not problems:
        lines.append("- Sin registros")
    else:
        for i, x in enumerate(problems, start=1):
            lines.append(
                f"{i}. {x.get('descripcion') or x.get('nombre') or 'Sin descripcion'} | "
                f"Estado: {x.get('estado') or 'No disponible'} | "
                f"Codigo: {x.get('codigo') or x.get('codigo_snomed') or 'No disponible'} | "
                f"Inicio: {x.get('fecha_inicio') or x.get('desde') or 'No disponible'}"
            )

    lines.extend(["", "TRATAMIENTO / MEDICACION ACTUAL"])
    treatment = history.get("tratamiento", [])
    if not treatment:
        lines.append("- Sin registros")
    else:
        for i, x in enumerate(treatment, start=1):
            lines.append(
                f"{i}. {x.get('medicamento') or x.get('nombre') or 'Sin nombre'} | "
                f"Estado: {x.get('estado') or 'No disponible'} | "
                f"Posologia: {x.get('posologia') or 'No disponible'}"
            )

    lines.extend(["", "ALERGIAS"])
    allergies = history.get("alergias", [])
    if not allergies:
        lines.append("- Sin registros")
    else:
        for i, x in enumerate(allergies, start=1):
            lines.append(
                f"{i}. {x.get('sustancia') or 'Sin sustancia'} | "
                f"Criticidad: {x.get('criticidad') or 'No disponible'} | "
                f"Manifestacion: {x.get('manifestacion') or 'No disponible'}"
            )

    lines.extend(["", "EPISODIOS / VISITAS"])
    episodes = history.get("episodios", [])
    if not episodes:
        lines.append("- Sin registros")
    else:
        for i, x in enumerate(episodes, start=1):
            lines.append(
                f"{i}. Fecha: {x.get('fecha') or 'No disponible'} | "
                f"Motivo: {x.get('motivo') or 'No disponible'} | "
                f"Resultado: {x.get('resultado') or 'No disponible'}"
            )

    lines.extend(["", "AGREGADOR HCIS ALL-SECTIONS (TRAZABILIDAD)"])
    all_sections = history.get("all_sections", [])
    if not all_sections:
        lines.append("- Sin fragmentos agregados")
    else:
        for i, f in enumerate(all_sections[:60], start=1):
            lines.append(
                f"{i}. [{f.get('source_section', 'seccion_desconocida')}] "
                f"{f.get('timestamp', 'Sin fecha')} | Autor: {f.get('author', 'No informado')} | "
                f"Confianza: {int((f.get('confidence', 0.6))*100)}% | "
                f"{'REVISAR MANUALMENTE' if f.get('manual_review') else 'OK'}"
            )
            lines.append(
                f"   Justificacion: \"{(f.get('text') or '')[:180]}\""
            )

    return "\n".join(lines)


def _escape_pdf_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Limita a latin-1 para compatibilidad sin librerias externas.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _build_simple_pdf(text: str) -> bytes:
    lines = text.splitlines()
    y = 790
    stream_lines = ["BT", "/F1 10 Tf", "40 790 Td"]
    first = True
    for raw in lines:
        line = _escape_pdf_text(raw[:140])
        if first:
            stream_lines.append(f"({line}) Tj")
            first = False
        else:
            stream_lines.append("0 -14 Td")
            stream_lines.append(f"({line}) Tj")
        y -= 14
        if y < 40:
            break
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    objects.append(
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n"
        + stream + b"\nendstream endobj"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj + b"\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii")
    )
    return bytes(pdf)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-service"}


@app.get("/")
async def dashboard():
    return FileResponse(DASHBOARD_PATH)


@app.get("/historial")
async def patient_history_page():
    return FileResponse(PATIENT_HISTORY_PATH)


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


@app.get("/fhir/casos/todos")
async def get_all_cases():
    """Devuelve todos los casos (pendientes + resueltos) para el dashboard."""
    cases = _load_cases()
    urgency_order = {"alta": 0, "media": 1, "baja": 2}
    cases.sort(key=lambda c: (
        0 if c.get("status") == "pending" else 1,
        urgency_order.get(c.get("triage", {}).get("urgencia", "baja"), 2),
    ))
    return cases


@app.get("/fhir/pacientes/{cip}/historial")
async def get_patient_history(cip: str):
    """
    Devuelve historial clínico por CIP:
    - Fuente principal: Bundle FHIR (local/prod según configuración).
    - Fallback: historial más reciente en cases.json.
    """
    history = await _resolve_hcis_history(cip)
    if history:
        history["documentos"] = [
            {
                "tipo": "texto_libre",
                "label": "Ver texto libre",
                "url": f"/fhir/pacientes/{cip}/historial/texto",
            },
            {
                "tipo": "pdf",
                "label": "Abrir PDF",
                "url": f"/fhir/pacientes/{cip}/historial/pdf",
            },
        ]
        return history

    raise HTTPException(status_code=404, detail="Paciente no encontrado")


@app.get("/fhir/pacientes/{cip}/master-record")
async def get_patient_master_record(cip: str):
    """
    Devuelve el JSON maestro normalizado del paciente para indexado, RAG y dashboard limpio.
    """
    bundle = await get_patient_bundle(cip)
    if not bundle:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return build_patient_master_record(bundle, cip)


@app.get("/fhir/pacientes/{cip}/historial/texto")
async def get_patient_history_text(cip: str):
    history = await _resolve_hcis_history(cip)
    if not history:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return PlainTextResponse(_history_to_free_text(history))


@app.get("/fhir/pacientes/{cip}/documentos/{doc_index}/{content_index}")
async def open_patient_document(cip: str, doc_index: int, content_index: int):
    """
    Abre adjuntos de DocumentReference (texto/PDF/binario) por índice de entrada/content.
    """
    bundle = await get_patient_bundle(cip)
    if not bundle:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    entries = bundle.get("entry", [])
    if doc_index < 0 or doc_index >= len(entries):
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    resource = entries[doc_index].get("resource", {})
    if resource.get("resourceType") != "DocumentReference":
        raise HTTPException(status_code=404, detail="La entrada no es un DocumentReference")

    contents = resource.get("content") or []
    if content_index < 0 or content_index >= len(contents):
        raise HTTPException(status_code=404, detail="Contenido de documento no encontrado")

    attachment = (contents[content_index] or {}).get("attachment") or {}
    ctype = attachment.get("contentType") or "application/octet-stream"
    title = attachment.get("title") or f"documento_{doc_index}_{content_index}"
    data_b64 = attachment.get("data")
    url = attachment.get("url")

    if isinstance(data_b64, str) and data_b64:
        try:
            raw = base64.b64decode(data_b64, validate=False)
        except Exception:
            raise HTTPException(status_code=400, detail="Adjunto base64 inválido")
        return Response(
            content=raw,
            media_type=ctype,
            headers={"Content-Disposition": f'inline; filename="{title}"'},
        )

    if isinstance(url, str) and url:
        # Si HCIS/FHIR devuelve enlace externo, delegamos la apertura.
        return RedirectResponse(url=url, status_code=307)

    raise HTTPException(status_code=404, detail="El documento no contiene datos ni URL")


@app.get("/fhir/pacientes/{cip}/historial/pdf")
async def get_patient_history_pdf(cip: str):
    history = await _resolve_hcis_history(cip)
    if not history:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    text = _history_to_free_text(history)
    pdf_bytes = _build_simple_pdf(text)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="historial_{cip}.pdf"'},
    )


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


async def _call_external_search_service(payload: dict) -> dict:
    """
    Proxy al buscador semántico/clásico externo (RAG) ya implementado por el equipo.
    """
    if not SEARCH_SERVICE_URL:
        return {
            "integration_status": "not_configured",
            "items": [],
            "message": "SEARCH_SERVICE_URL no está configurado.",
        }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{SEARCH_SERVICE_URL}/search", json=payload)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                return data
            return {"integration_status": "ok", "items": data if isinstance(data, list) else []}
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Buscador externo no disponible: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Buscador externo devolvió error HTTP: {exc}") from exc


@app.get("/fhir/pacientes/{cip}/search")
async def search_patient_history(
    cip: str,
    q: str = Query(default="", description="Consulta de búsqueda"),
    mode: str = Query(default="hybrid", description="classic|semantic|hybrid"),
    section_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    author: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Endpoint de integración con el buscador RAG del equipo.
    No implementa scoring local: delega en SEARCH_SERVICE_URL.
    """
    bundle = await get_patient_bundle(cip)
    if not bundle:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    master_record = build_patient_master_record(bundle, cip)
    payload = {
        "cip": cip,
        "query": q,
        "mode": mode,
        "filters": {
            "section_type": section_type,
            "date_from": date_from,
            "date_to": date_to,
            "author": author,
            "min_confidence": min_confidence,
            "limit": limit,
        },
        "master_record": master_record,
    }
    return await _call_external_search_service(payload)
