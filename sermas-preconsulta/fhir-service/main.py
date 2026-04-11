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
import logging
import os
import re
import shutil
import subprocess
import uuid
import base64
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fhir-service")

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

# Raíz del proyecto drAId (tres niveles por encima del fhir-service)
_DRAID_ROOT = Path(__file__).parent.parent.parent
_FHIR_SERVICE_DIR = Path(__file__).parent
CASES_FILE.parent.mkdir(parents=True, exist_ok=True)


def _resolve_documents_root() -> Path:
    env_path = os.getenv("HCIS_DOCUMENTS_DIR")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend([
        _FHIR_SERVICE_DIR / "data" / "hcis_master" / "documents",
        _DRAID_ROOT / "sermas-preconsulta" / "fhir-service" / "data" / "hcis_master" / "documents",
    ])

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

    # Default to the local fhir-service path even if not created yet.
    return (_FHIR_SERVICE_DIR / "data" / "hcis_master" / "documents").resolve()


def _resolve_patient_folder(cip: str) -> Path:
    raw = (cip or "").strip()
    normalized = re.sub(r"[^0-9A-Za-z_-]", "", raw)
    candidates = [raw, normalized]

    # If CIP comes as reference-like token (e.g., Patient/2800001234), use last chunk.
    if "/" in raw:
        candidates.append(raw.split("/")[-1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        folder = _MEDICAL_DATA_DIR / candidate
        if folder.is_dir():
            return folder

    # Fallback to normalized name for deterministic error messages.
    return _MEDICAL_DATA_DIR / (normalized or raw)


def _find_indexable_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return [
        f for f in sorted(folder.rglob("*"))
        if f.is_file() and f.suffix.lower() in {".txt", ".pdf"}
    ]


def _run_medical_search_index(cip: str, patient_folder: Path, collection_name: str, persist_dir: str) -> tuple[int, str, str]:
    """
    Ejecuta indexado con la misma lógica del comando CLI:
      uv run medical-search index <folder> --patient-id <cip>
    Se implementa vía python -m medical_search para evitar depender del entrypoint.
    """
    import sys

    cmd = [
        sys.executable,
        "-m",
        "medical_search",
        "index",
        str(patient_folder),
        "--patient-id",
        cip,
        "--persist-dir",
        persist_dir,
        "--collection",
        collection_name,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _is_chroma_storage_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = [
        "nothing found on disk",
        "error creating hnsw segment reader",
        "segment",
    ]
    return any(marker in msg for marker in markers)


def _reset_chroma_storage_for_collection(persist_dir: str, collection_name: str) -> None:
    import chromadb as _chromadb

    try:
        client = _chromadb.PersistentClient(path=persist_dir)
        client.delete_collection(collection_name)
    except Exception:
        pass

    # As a hard reset for corrupted local state in hackathon mode.
    try:
        if Path(persist_dir).exists():
            shutil.rmtree(persist_dir, ignore_errors=True)
    except Exception:
        pass

    Path(persist_dir).mkdir(parents=True, exist_ok=True)


# ── Modelos ──────────────────────────────────────────────────────────────────

class PreConsultaRequest(BaseModel):
    session_id: str
    cip: str | None
    symptoms: dict
    caller_phone: str | None = None  # número del paciente (From de Twilio)


class CaseAction(BaseModel):
    action: str  # "call_now" | "keep_appointment" | "refer_emergency"


class RecomputeTriageRequest(BaseModel):
    selected_evidence: list[dict] = []


class SemanticSummaryRequest(BaseModel):
    query: str
    results: list[dict]


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


# ── Lectura de documentos desde carpeta medical_search/data/{cip}/ ────────────

_MEDICAL_DATA_DIR = _resolve_documents_root()

_STEM_TO_SECTION: list[tuple[str, str, str]] = [
    ("nota_urgencias",           "urgencias",                  "Nota de Urgencias"),
    ("informe_urgencias",        "urgencias",                  "Informe Urgencias"),
    ("informe_alta",             "informes_alta_evolucion",    "Informe de Alta"),
    ("resultado_laboratorio",    "laboratorio",                "Resultado Laboratorio"),
    ("resultado_analitica",      "laboratorio",                "Analítica"),
    ("resultado_ecg",            "informes_pruebas",           "ECG"),
    ("resultado_espirometria",   "informes_pruebas",           "Espirometría"),
    ("informe_radiologia",       "pruebas_imagen",             "Informe Radiología"),
    ("informe_tac",              "pruebas_imagen",             "TAC"),
    ("nota_evolucion",           "consultas_externas",         "Nota de Especialista"),
    ("nota_atencion_primaria",   "consultas_externas",         "Atención Primaria"),
    ("nota_medicina_interna",    "consultas_externas",         "Medicina Interna"),
    ("control_obstetrico",       "consultas_externas",         "Control Obstétrico"),
    ("nota_enfermeria",          "planes_cuidados",            "Plan Enfermería"),
    ("plan_cuidados",            "planes_cuidados",            "Plan de Cuidados"),
    ("historia_clinica",         "informes_alta_evolucion",    "Historia Clínica Resumida"),
]


def _stem_to_section(stem: str) -> tuple[str, str]:
    sl = stem.lower()
    for keyword, section, label in _STEM_TO_SECTION:
        if keyword in sl:
            return section, label
    return "anotaciones_notas_libres", "Documento"


def _extract_date_from_stem(stem: str) -> str:
    import re
    # Pattern YYYY-MM-DD in filename
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    if m:
        return m.group(1)
    # Pattern YYYYMMDD
    for token in stem.replace("-", "_").split("_"):
        try:
            from datetime import datetime as _dt
            return _dt.strptime(token, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return ""


def _read_folder_as_sections(cip: str) -> list[dict]:
    """
    Lee todos los TXT/PDF de medical_search/data/{cip}/ y los devuelve
    como fragmentos all_sections listos para el historial del dashboard.
    """
    folder = _resolve_patient_folder(cip)
    if not folder.is_dir():
        return []

    try:
        import sys as _sys
        _sys.path.insert(0, str(_DRAID_ROOT))
        import fitz as _fitz
        _fitz_ok = True
    except ImportError:
        _fitz_ok = False

    sections: list[dict] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()
        if suffix not in {".txt", ".pdf"}:
            continue
        try:
            if suffix == ".txt":
                text = f.read_text(encoding="utf-8", errors="ignore").strip()
            elif _fitz_ok:
                with _fitz.open(str(f)) as doc:
                    text = "\n".join(p.get_text("text").strip() for p in doc).strip()
            else:
                continue
        except Exception:
            continue

        if not text:
            continue

        source_section, section_label = _stem_to_section(f.stem)
        sections.append({
            "source_section": source_section,
            "section_type":   section_label,
            "resource_type":  section_label,
            "filename":       f.name,
            "timestamp":      _extract_date_from_stem(f.stem),
            "author":         "No informado",
            "text":           text,
            "confidence":     0.95 if suffix == ".txt" else 0.90,
            "manual_review":  False,
        })

    return sections


async def _resolve_hcis_history(cip: str) -> dict | None:
    # Intentar leer desde carpeta de documentos del paciente
    folder_sections = _read_folder_as_sections(cip)
    cached_history = _get_cached_history_for_cip(cip)

    bundle = await get_patient_bundle(cip)
    if bundle:
        master_record = build_patient_master_record(bundle, cip)
        base = to_legacy_history_view(master_record, cip)
        # Si hay carpeta de documentos, usarla como fuente principal de all_sections
        if folder_sections:
            base["all_sections"] = folder_sections
        elif not base.get("all_sections"):
            base["all_sections"] = _build_fragments_from_bundle(bundle, cip)
        if not base.get("catalogo_hcis"):
            base["catalogo_hcis"] = _hcis_section_catalog()
        return base

    # Sin bundle FHIR — si hay carpeta de documentos, construir historial mínimo
    if folder_sections:
        cached_patient = (cached_history or {}).get("paciente", {})
        return {
            "estructura": "HCIS",
            "paciente": {
                **cached_patient,
                "cip": cached_patient.get("cip") or cip,
            },
            "all_sections": folder_sections,
            "catalogo_hcis": _hcis_section_catalog(),
        }

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


@app.get("/fhir/casos/{case_id}")
async def get_case(case_id: str):
    cases = _load_cases()
    for case in cases:
        if case.get("id") == case_id:
            return case
    raise HTTPException(status_code=404, detail="Caso no encontrado")


@app.post("/fhir/casos/{case_id}/recompute-triage")
async def recompute_case_triage(case_id: str, body: RecomputeTriageRequest):
    """
    Recalcula el triaje del caso usando síntomas originales + evidencia seleccionada del historial.
    """
    cases = _load_cases()
    for case in cases:
        if case.get("id") != case_id:
            continue

        symptoms = case.get("symptoms") or {}
        history = case.get("history") or {}
        selected = body.selected_evidence or []
        history_enhanced = dict(history)
        history_enhanced["selected_evidence"] = selected[:20]

        triage = await _call_llm_service(symptoms, history_enhanced)
        case["triage"] = triage
        case["selected_evidence"] = selected[:20]
        case["triage_curated_at"] = datetime.now().isoformat()
        _save_cases(cases)

        return {
            "id": case.get("id"),
            "triage": triage,
            "selected_evidence_count": len(selected),
            "triage_curated_at": case["triage_curated_at"],
        }

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


_CHROMA_DIR = _DRAID_ROOT / "medical_search" / ".chroma_medical"


async def _local_medical_search_for_cip(cip: str, query: str, top_k: int = 10, index_only: bool = False) -> dict:
    """
    Búsqueda semántica local usando medical_search (ChromaDB + spaCy).
    Indexa automáticamente los documentos del paciente si la colección está vacía.
    """
    try:
        import sys
        if str(_DRAID_ROOT) not in sys.path:
            sys.path.insert(0, str(_DRAID_ROOT))

        import chromadb as _chromadb
        from medical_search.search import MedicalSearcher

        cip = (cip or "").strip()
        collection_name = f"medical_notes_{cip}"
        persist_dir = str(_CHROMA_DIR)
        patient_folder = _resolve_patient_folder(cip)

        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("[search] cip=%s query=%r collection=%s", cip, query, collection_name)

        client = _chromadb.PersistentClient(path=persist_dir)
        try:
            col = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            chunks_before = col.count()
        except Exception as exc:
            if not _is_chroma_storage_error(exc):
                raise

            logger.warning("[search] chroma storage corrupted for %s, rebuilding local index storage", collection_name)
            _reset_chroma_storage_for_collection(persist_dir, collection_name)
            client = _chromadb.PersistentClient(path=persist_dir)
            col = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            chunks_before = col.count()

        indexing_required = chunks_before == 0
        indexing_performed = False
        indexed_files = 0
        failed_files = 0

        logger.info("[search] collection %s has %d chunks", collection_name, chunks_before)

        if indexing_required:
            if not patient_folder.exists() or not patient_folder.is_dir():
                logger.warning("[search] patient folder not found for cip=%s at %s", cip, patient_folder)
                return {
                    "integration_status": "no_documents",
                    "source": "medical_search",
                    "items": [],
                    "message": f"No existe carpeta de documentos del paciente para indexar en: {patient_folder}",
                    "documents_path": str(patient_folder),
                    "indexing": {
                        "required": True,
                        "performed": False,
                        "indexed_files": 0,
                        "failed_files": 0,
                    },
                }

            files = _find_indexable_files(patient_folder)
            if not files:
                logger.warning("[search] no indexable files for cip=%s in %s", cip, patient_folder)
                return {
                    "integration_status": "no_documents",
                    "source": "medical_search",
                    "items": [],
                    "message": "No hay archivos .txt/.pdf para indexar.",
                    "documents_path": str(patient_folder),
                    "indexing": {
                        "required": True,
                        "performed": False,
                        "indexed_files": 0,
                        "failed_files": 0,
                    },
                }

            logger.info("[search] indexing %d files from %s", len(files), patient_folder)
            rc, stdout, stderr = _run_medical_search_index(
                cip=cip,
                patient_folder=patient_folder,
                collection_name=collection_name,
                persist_dir=persist_dir,
            )

            indexed_files = len([line for line in stdout.splitlines() if line.strip().startswith("Indexed:")])
            failed_files = len([line for line in stdout.splitlines() if line.strip().startswith("[ERROR]")])
            if rc != 0 and indexed_files == 0:
                logger.warning("[search] medical_search index command failed rc=%s stderr=%s", rc, stderr.strip())
                return {
                    "integration_status": "error",
                    "source": "medical_search",
                    "items": [],
                    "message": f"Fallo indexando con medical_search: {stderr.strip() or stdout.strip() or 'error desconocido'}",
                    "documents_path": str(patient_folder),
                    "indexing": {
                        "required": True,
                        "performed": True,
                        "indexed_files": indexed_files,
                        "failed_files": max(failed_files, len(files) - indexed_files),
                    },
                }

            indexing_performed = True
            logger.info("[search] indexing complete — collection now has %d chunks", col.count())

        chunks_after = col.count()
        if chunks_after == 0:
            logger.warning("[search] no documents/chunks available for cip=%s", cip)
            return {
                "integration_status": "no_documents",
                "source": "medical_search",
                "items": [],
                "message": "No hay chunks indexados para este paciente.",
                "documents_path": str(patient_folder),
                "indexing": {
                    "required": indexing_required,
                    "performed": indexing_performed,
                    "indexed_files": indexed_files,
                    "failed_files": failed_files,
                },
            }

        if index_only:
            message = "Indice disponible para este paciente."
            if indexing_performed:
                message = f"Indexacion completada: {indexed_files} ficheros indexados, {failed_files} con error."

            return {
                "integration_status": "ok",
                "source": "medical_search",
                "items": [],
                "message": message,
                "documents_path": str(patient_folder),
                "indexing": {
                    "required": indexing_required,
                    "performed": indexing_performed,
                    "indexed_files": indexed_files,
                    "failed_files": failed_files,
                },
            }

        searcher = MedicalSearcher(persist_dir=persist_dir, collection_name=collection_name)
        try:
            hits = searcher.search(query, top_k=top_k)
        except Exception as exc:
            if not _is_chroma_storage_error(exc):
                raise

            logger.warning("[search] chroma query failed due to storage inconsistency, rebuilding and reindexing")
            _reset_chroma_storage_for_collection(persist_dir, collection_name)

            files = _find_indexable_files(patient_folder)
            if not files:
                raise

            rc, stdout, stderr = _run_medical_search_index(
                cip=cip,
                patient_folder=patient_folder,
                collection_name=collection_name,
                persist_dir=persist_dir,
            )
            indexed_files = max(indexed_files, len([line for line in stdout.splitlines() if line.strip().startswith("Indexed:")]))
            failed_files = max(failed_files, len([line for line in stdout.splitlines() if line.strip().startswith("[ERROR]")]))
            if rc != 0 and indexed_files == 0:
                raise RuntimeError(stderr.strip() or stdout.strip() or "Fallo reindexando tras reset de Chroma")

            searcher = MedicalSearcher(persist_dir=persist_dir, collection_name=collection_name)
            hits = searcher.search(query, top_k=top_k)

        logger.info("[search] query=%r returned %d hits", query, len(hits))

        from pathlib import Path as _Path
        items = []
        for hit in hits:
            src_path = hit.metadata.get("source_path", "")
            filename = _Path(src_path).name if src_path else hit.doc_id
            doc_date = hit.metadata.get("document_date", "")
            items.append({
                "type": "documento",
                "date": doc_date,
                "origin": filename,
                "text": hit.text,
                "source_section": "medical_search",
                "confidence": round(hit.score, 4),
                "score": round(hit.score, 4),
            })

        message = None
        if indexing_performed:
            message = f"Indexacion completada: {indexed_files} ficheros indexados, {failed_files} con error."

        return {
            "integration_status": "ok",
            "source": "medical_search",
            "items": items,
            "message": message,
            "documents_path": str(patient_folder),
            "indexing": {
                "required": indexing_required,
                "performed": indexing_performed,
                "indexed_files": indexed_files,
                "failed_files": failed_files,
            },
        }
    except Exception as exc:
        logger.exception("[search] local medical_search failed for cip=%s", cip)
        return {
            "integration_status": "error",
            "source": "medical_search",
            "items": [],
            "message": f"Fallo en medical_search: {exc}",
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


def _format_results_for_summary_prompt(results: list[dict], limit: int = 12) -> str:
    lines: list[str] = []
    for idx, item in enumerate(results[:limit], start=1):
        origin = str(item.get("origin") or "unknown")
        score = item.get("score")
        score_txt = f"{float(score):.3f}" if isinstance(score, (int, float)) else "n/a"
        text = str(item.get("text") or "").strip().replace("\n", " ")
        if len(text) > 520:
            text = text[:520].rstrip() + "..."
        lines.append(f"{idx}. origin={origin} | score={score_txt} | snippet={text}")
    return "\n".join(lines)


@app.post("/fhir/pacientes/{cip}/search/summary")
async def summarize_search_results(cip: str, payload: SemanticSummaryRequest):
    """
    Generates an on-demand English summary from semantic search results.
    """
    query = (payload.query or "").strip()
    results = payload.results or []
    if not query:
        raise HTTPException(status_code=400, detail="Query is required to generate a summary.")
    if not results:
        raise HTTPException(status_code=400, detail="At least one search result is required.")

    model_name = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_bin = os.path.expanduser(os.getenv("OLLAMA_BIN", "~/PLN/bin/ollama"))

    try:
        from ollama import AsyncClient
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Python package 'ollama' is not available: {exc}",
        ) from exc

    system_prompt = (
        "You are a clinical summarization assistant. "
        "Write in English only. "
        "Summarize semantic-search snippets for a physician. "
        "Do not invent facts. If evidence is weak or conflicting, state that clearly. "
        "Keep it concise and actionable."
    )
    user_prompt = (
        f"Patient CIP: {cip}\n"
        f"Search query: {query}\n\n"
        "Semantic search results:\n"
        f"{_format_results_for_summary_prompt(results)}\n\n"
        "Output format:\n"
        "1) One short paragraph with the key clinical picture.\n"
        "2) Bullet list of 3-5 relevant findings.\n"
        "3) One line with risks/uncertainties from the evidence quality.\n"
        "4) One line with suggested next review step."
    )

    try:
        client = AsyncClient(host=ollama_host)
        response = await client.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0.2},
        )
        summary = ((response or {}).get("message") or {}).get("content", "").strip()
        if not summary:
            raise RuntimeError("Empty response from model")
        return {
            "integration_status": "ok",
            "summary": summary,
            "model": model_name,
            "host": ollama_host,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Ollama summary generation failed. "
                f"Verify Ollama is running and model '{model_name}' is available. "
                f"Expected binary path: {ollama_bin}. Error: {exc}"
            ),
        ) from exc


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
    Búsqueda semántica sobre los documentos del paciente.
    Usa medical_search (ChromaDB + spaCy) localmente cuando SEARCH_SERVICE_URL no está configurado.
    """
    if not q.strip():
        return {"integration_status": "ok", "source": "medical_search", "items": []}

    if not SEARCH_SERVICE_URL:
        return await _local_medical_search_for_cip(cip, q, top_k=limit)

    # Delegar en servicio externo
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
    try:
        return await _call_external_search_service(payload)
    except HTTPException as exc:
        # Fallback transparente a búsqueda local para no bloquear el dashboard
        logger.warning("[search] external search failed, fallback to local medical_search: %s", exc.detail)
        local = await _local_medical_search_for_cip(cip, q, top_k=limit)
        if isinstance(local, dict):
            local["source"] = "medical_search_fallback"
            local["fallback_reason"] = str(exc.detail)
        return local


@app.post("/fhir/pacientes/{cip}/search/index")
async def warmup_patient_search_index(cip: str):
    """
    Dispara indexación local de documentos del paciente para reducir latencia
    de la primera búsqueda en historial.html.
    """
    return await _local_medical_search_for_cip(cip, query="", top_k=1, index_only=True)
