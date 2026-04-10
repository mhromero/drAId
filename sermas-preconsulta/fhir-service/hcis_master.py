"""
Construcción del Patient Master Record (PMR) a partir de Bundle FHIR.

Incluye:
- Contrato PMR v1 (alineado con bloques HCDSNS/RD 1093/2010)
- Reglas explícitas de extracción por tipo documental/recurso
- Resolución de conflictos clínicos frecuentes
- Checklist de calidad para validar pacientes sintéticos de demo
"""

from __future__ import annotations

import base64
import uuid
import unicodedata
from datetime import datetime

REQUIRED_HCDSNS_DOC_TYPES = [
    "ICA",   # Informe clínico de alta
    "ICCE",  # Consulta externa
    "ICU",   # Urgencias
    "ICAP",  # Atención primaria
    "ICE",   # Cuidados de enfermería
    "IRPL",  # Resultados laboratorio
    "IRPI",  # Resultados imagen
    "IROPD", # Otras pruebas diagnósticas
    "HCR",   # Historia clínica resumida
]

DOC_TYPE_HINTS = {
    "alta": "ICA",
    "urgenc": "ICU",
    "atencion primaria": "ICAP",
    "consulta externa": "ICCE",
    "enfermer": "ICE",
    "laboratorio": "IRPL",
    "radiolog": "IRPI",
    "imagen": "IRPI",
    "ecg": "IROPD",
    "electro": "IROPD",
    "espirom": "IROPD",
    "resum": "HCR",
}


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _text(value: str | None) -> str:
    return (value or "").strip()


def _norm(value: str | None) -> str:
    text = _text(value).lower()
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def _pick_cip(patient: dict, fallback_cip: str) -> str:
    for i in patient.get("identifier", []):
        system = _norm(i.get("system"))
        if "cip" in system or "sermas" in system:
            if i.get("value"):
                return i["value"]
    return fallback_cip


def _pick_patient_name(patient: dict) -> tuple[str, str, str | None]:
    n = (patient.get("name") or [{}])[0]
    given = " ".join(n.get("given") or [])
    family = _text(n.get("family"))
    parts = family.split()
    fam1 = parts[0] if parts else family
    fam2 = parts[1] if len(parts) > 1 else None
    return _text(given), fam1, fam2


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
            return value
    period = resource.get("period") or {}
    if isinstance(period.get("start"), str) and period.get("start"):
        return period["start"]
    return None


def _extract_author(resource: dict) -> str | None:
    recorder = resource.get("recorder") or {}
    if recorder.get("display"):
        return recorder["display"]
    for key in ["asserter", "requester", "performer", "participant", "author"]:
        value = resource.get(key)
        if isinstance(value, dict) and value.get("display"):
            return value["display"]
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                actor = first.get("actor") or first.get("individual") or first
                if isinstance(actor, dict) and actor.get("display"):
                    return actor["display"]
    return None


def _add_source_ref(record: dict, *, section: str, entity: str, source_id: str, timestamp: str | None,
                    author: str | None, confidence: float, manual_review: bool) -> str:
    sid = _new_id("src")
    record["source_refs"].append({
        "id": sid,
        "source_system": "FHIR",
        "source_entity": entity,
        "source_id": source_id,
        "retrieved_at": now_iso(),
        "author": author,
        "source_section": section,
        "confidence": round(confidence, 2),
        "manual_review": manual_review,
        "timestamp": timestamp,
    })
    return sid


def _add_evidence(record: dict, *, doc_id: str, quote: str, page: int = 1, section: str | None = None) -> str:
    text = _text(quote)
    if not text:
        text = "Sin evidencia textual"
    eid = _new_id("ev")
    record["evidence_spans"].append({
        "id": eid,
        "doc_id": doc_id,
        "section": section,
        "text_quote": text[:350],
        "char_start": 0,
        "char_end": min(len(text), 350),
        "page": page,
        "captured_at": now_iso(),
    })
    return eid


def _doc_type_from_text(title: str, category: str, fallback: str = "OTHER") -> str:
    haystack = f"{_norm(title)} {_norm(category)}"
    for hint, code in DOC_TYPE_HINTS.items():
        if hint in haystack:
            return code
    return fallback


def extraction_playbook() -> dict:
    """
    Reglas de extracción por recurso FHIR y tipo documental esperado.
    """
    return {
        "Patient": {
            "targets": ["patient_demographics"],
            "doc_type_default": "HCR",
            "notes": "Identificadores CIP/CIP-AUT/NHC, nombre, sexo, fecha nacimiento, contacto.",
        },
        "Encounter": {
            "targets": ["encounters", "clinical_notes"],
            "doc_type_default": "ICCE",
            "notes": "Clasificar urgencias/hospitalización/consulta/AP por class/service/reasonCode.",
        },
        "Condition": {
            "targets": ["diagnoses", "active_problems"],
            "doc_type_default": "HCR",
            "notes": "Mapear clinicalStatus/verificationStatus y códigos clínicos.",
        },
        "Procedure": {
            "targets": ["procedures"],
            "doc_type_default": "IROPD",
            "notes": "Marcar is_surgery cuando category/text indique cirugía o quirófano.",
        },
        "MedicationRequest": {
            "targets": ["medications"],
            "doc_type_default": "HCR",
            "notes": "Priorizar fármacos activos y conservar posología textual.",
        },
        "AllergyIntolerance": {
            "targets": ["allergies_adrs"],
            "doc_type_default": "HCR",
            "notes": "No eliminar registros vacíos: guardar null_flavor y trazabilidad.",
        },
        "DiagnosticReport": {
            "targets": ["lab_results", "imaging_reports", "other_diagnostic_tests"],
            "doc_type_default": "IROPD",
            "notes": "Clasificar por categoría: lab->IRPL, imagen->IRPI, resto->IROPD.",
        },
        "Observation": {
            "targets": ["lab_results", "clinical_notes"],
            "doc_type_default": "IRPL",
            "notes": "Resultados aislados de laboratorio/constantes y notas complementarias.",
        },
        "DocumentReference": {
            "targets": ["document_index", "attachments", "clinical_notes"],
            "doc_type_default": "OTHER",
            "notes": "Mantener adjuntos PDF/texto y extracción textual parcial para búsqueda.",
        },
        "Composition": {
            "targets": ["discharge_summaries", "clinical_notes", "document_index"],
            "doc_type_default": "ICA",
            "notes": "Documentos clínicos firmados (alta/evolución/resumen).",
        },
        "CarePlan": {
            "targets": ["nursing_care"],
            "doc_type_default": "ICE",
            "notes": "Planes y cuidados de enfermería.",
        },
    }


def _encounter_type(resource: dict) -> str:
    cls = _norm((resource.get("class") or {}).get("code"))
    reason = _norm(((resource.get("reasonCode") or [{}])[0] or {}).get("text"))
    service = _norm((resource.get("serviceType") or {}).get("text"))
    hay = f"{cls} {reason} {service}"
    if any(x in hay for x in ["urgenc", "emerg", "er", "ed"]):
        return "emergency"
    if any(x in hay for x in ["inpatient", "hospital", "ward", "imp"]):
        return "inpatient"
    if any(x in hay for x in ["primary", "atencion primaria", "ap"]):
        return "primary-care"
    return "outpatient"


def _doc_type_from_resource(resource: dict, rtype: str) -> str:
    if rtype == "Composition":
        t = ((resource.get("type") or {}).get("text") or "")
        return _doc_type_from_text(t, "", fallback="ICA")
    if rtype == "Encounter":
        et = _encounter_type(resource)
        if et == "emergency":
            return "ICU"
        if et == "primary-care":
            return "ICAP"
        if et == "inpatient":
            return "ICA"
        return "ICCE"
    if rtype == "DiagnosticReport":
        cat = _norm((((resource.get("category") or [{}])[0] or {}).get("text")))
        if "lab" in cat or "laborat" in cat:
            return "IRPL"
        if "imag" in cat or "radiolog" in cat:
            return "IRPI"
        return "IROPD"
    if rtype == "Observation":
        return "IRPL"
    if rtype == "CarePlan":
        return "ICE"
    if rtype == "DocumentReference":
        title = ""
        content = (resource.get("content") or [{}])[0]
        att = (content or {}).get("attachment") or {}
        title = att.get("title") or ""
        typ = ((resource.get("type") or {}).get("text") or "")
        return _doc_type_from_text(title, typ, fallback="OTHER")
    return "HCR"


def _codeable(coding_owner: dict) -> dict:
    codings = coding_owner.get("coding") or []
    first = codings[0] if codings else {}
    return {
        "system": first.get("system") or "free",
        "value": first.get("code"),
        "display": first.get("display") or coding_owner.get("text") or "No especificado",
    }


def _resource_date(resource: dict) -> str | None:
    ts = _extract_timestamp(resource)
    if not ts:
        return None
    return ts[:10]


def _build_base_record(cip: str) -> dict:
    ts = now_iso()
    return {
        "schema_version": "1.0.0",
        "record_id": _new_id("pmr"),
        "created_at": ts,
        "updated_at": ts,
        "patient_demographics": {
            "patient_id": cip,
            "cip_sns": cip,
            "cip_aut": None,
            "nhc": None,
            "dni_nie": None,
            "name": "",
            "family_name_1": "",
            "family_name_2": None,
            "birth_date": None,
            "sex_at_birth": "unknown",
            "phones": [],
            "email": None,
            "address": {
                "street_type": None,
                "street_name": None,
                "street_number": None,
                "postal_code": None,
                "city": None,
                "province": None,
                "country_iso3166_1": "ES",
            },
            "primary_care_center": {"regcess_code": None, "name": None},
        },
        "document_index": [],
        "encounters": [],
        "diagnoses": [],
        "active_problems": [],
        "procedures": [],
        "medications": [],
        "allergies_adrs": [],
        "lab_results": [],
        "imaging_reports": [],
        "other_diagnostic_tests": [],
        "clinical_notes": [],
        "discharge_summaries": [],
        "nursing_care": [],
        "attachments": [],
        "evidence_spans": [],
        "source_refs": [],
        "all_sections": [],
        "traceability": {
            "source_system": "FHIR",
            "build_mode": "all-sections",
        },
        "conflict_resolution": {
            "policy": "recency+clinical-priority",
            "conflicts": [],
        },
    }


def _add_section_fragment(record: dict, *, doc_id: str, section_type: str, text: str,
                          date: str | None, author: str | None, codes: list[dict],
                          confidence: float = 0.85, manual_review: bool = False,
                          source_section: str | None = None, resource_type: str | None = None,
                          document_access: dict | None = None) -> None:
    if not _text(text):
        return
    fragment = {
        "section_id": _new_id("sec"),
        "doc_id": doc_id,
        "section_type": section_type,
        "text": text[:500],
        "date": date,
        "author": author,
        "codes": codes,
        "embedding_ready": True,
        "source_section": source_section or section_type,
        "resource_type": resource_type,
        "timestamp": date,
        "confidence": round(confidence, 2),
        "manual_review": manual_review,
    }
    if document_access:
        fragment["document_access"] = document_access
    record["all_sections"].append(fragment)


def _resolve_diagnosis_conflicts(record: dict) -> None:
    merged = {}
    for dx in record["diagnoses"]:
        code_key = _norm((dx.get("code") or {}).get("value"))
        disp_key = _norm((dx.get("code") or {}).get("display"))
        key = code_key or disp_key
        if not key:
            key = _new_id("dxkey")
        prev = merged.get(key)
        if not prev:
            merged[key] = dx
            continue

        prev_status = prev.get("clinical_status")
        cur_status = dx.get("clinical_status")
        status_rank = {"active": 3, "recurrence": 3, "remission": 2, "resolved": 1, "unknown": 0}

        prev_date = prev.get("onset_date") or ""
        cur_date = dx.get("onset_date") or ""

        chosen = prev
        if status_rank.get(cur_status, 0) > status_rank.get(prev_status, 0):
            chosen = dx
        elif status_rank.get(cur_status, 0) == status_rank.get(prev_status, 0) and cur_date > prev_date:
            chosen = dx

        if chosen is not prev:
            record["conflict_resolution"]["conflicts"].append({
                "type": "diagnosis_duplicate",
                "key": key,
                "kept": chosen["id"],
                "dropped": prev["id"],
            })
        merged[key] = chosen

    record["diagnoses"] = list(merged.values())
    record["active_problems"] = [
        dx for dx in record["diagnoses"] if dx.get("clinical_status") in {"active", "recurrence"}
    ]


def _resolve_medication_conflicts(record: dict) -> None:
    merged = {}
    for med in record["medications"]:
        drug = med.get("drug") or {}
        key = _norm(drug.get("code")) or _norm(drug.get("display"))
        if not key:
            key = _new_id("medkey")
        prev = merged.get(key)
        if not prev:
            merged[key] = med
            continue

        status_rank = {"active": 4, "on-hold": 3, "completed": 2, "stopped": 1, "unknown": 0}
        prev_rank = status_rank.get(prev.get("status"), 0)
        cur_rank = status_rank.get(med.get("status"), 0)

        prev_date = prev.get("start_date") or ""
        cur_date = med.get("start_date") or ""
        chosen = prev
        if cur_rank > prev_rank or (cur_rank == prev_rank and cur_date > prev_date):
            chosen = med

        if prev.get("status") != med.get("status"):
            chosen["manual_review"] = True
            record["conflict_resolution"]["conflicts"].append({
                "type": "medication_status_conflict",
                "key": key,
                "status_seen": [prev.get("status"), med.get("status")],
                "kept": chosen.get("id"),
            })
        merged[key] = chosen

    record["medications"] = list(merged.values())


def _resolve_allergy_conflicts(record: dict) -> None:
    merged = {}
    for alg in record["allergies_adrs"]:
        agent = alg.get("agent") or {}
        key = _norm(agent.get("value")) or _norm(agent.get("display"))
        if not key:
            key = _new_id("algkey")
        prev = merged.get(key)
        if not prev:
            merged[key] = alg
            continue

        criticality_rank = {"high": 3, "low": 2, "unable-to-assess": 1, "unknown": 0, None: 0}
        prev_rank = criticality_rank.get(prev.get("criticality"), 0)
        cur_rank = criticality_rank.get(alg.get("criticality"), 0)

        prev_date = prev.get("recorded_date") or ""
        cur_date = alg.get("recorded_date") or ""

        chosen = prev
        if cur_rank > prev_rank or (cur_rank == prev_rank and cur_date > prev_date):
            chosen = alg

        if prev.get("verification_status") != alg.get("verification_status"):
            chosen["manual_review"] = True
            record["conflict_resolution"]["conflicts"].append({
                "type": "allergy_verification_conflict",
                "key": key,
                "verification_seen": [prev.get("verification_status"), alg.get("verification_status")],
                "kept": chosen.get("id"),
            })
        merged[key] = chosen

    record["allergies_adrs"] = list(merged.values())


def build_patient_master_record(bundle: dict, cip: str) -> dict:
    """Construye patient_master_record.json v1 desde un Bundle FHIR."""
    record = _build_base_record(cip)
    entries = bundle.get("entry", [])

    patient_resource = None
    for entry in entries:
        r = entry.get("resource") or {}
        if r.get("resourceType") == "Patient":
            patient_resource = r
            break

    if patient_resource:
        given, fam1, fam2 = _pick_patient_name(patient_resource)
        addr = (patient_resource.get("address") or [{}])[0]
        record["patient_demographics"].update({
            "patient_id": patient_resource.get("id") or cip,
            "cip_sns": _pick_cip(patient_resource, cip),
            "name": given,
            "family_name_1": fam1,
            "family_name_2": fam2,
            "birth_date": patient_resource.get("birthDate"),
            "sex_at_birth": patient_resource.get("gender") or "unknown",
            "phones": [x.get("value") for x in patient_resource.get("telecom", []) if x.get("system") == "phone" and x.get("value")],
            "email": next((x.get("value") for x in patient_resource.get("telecom", []) if x.get("system") == "email" and x.get("value")), None),
            "address": {
                "street_type": None,
                "street_name": (addr.get("line") or [None])[0],
                "street_number": None,
                "postal_code": addr.get("postalCode"),
                "city": addr.get("city"),
                "province": addr.get("state"),
                "country_iso3166_1": addr.get("country") or "ES",
            },
        })

    for idx, entry in enumerate(entries):
        resource = entry.get("resource") or {}
        rtype = resource.get("resourceType")
        if not rtype:
            continue

        source_id = resource.get("id") or f"{rtype}-{idx}"
        timestamp = _extract_timestamp(resource)
        author = _extract_author(resource)
        doc_type = _doc_type_from_resource(resource, rtype)

        doc_id = _new_id("doc")
        src_id = _add_source_ref(
            record,
            section=rtype.lower(),
            entity=rtype,
            source_id=source_id,
            timestamp=timestamp,
            author=author,
            confidence=0.9 if timestamp else 0.72,
            manual_review=not bool(timestamp),
        )

        title = f"{rtype} {idx + 1}"
        if rtype == "DocumentReference":
            content = (resource.get("content") or [{}])[0]
            att = (content or {}).get("attachment") or {}
            title = att.get("title") or title
        elif rtype == "Composition":
            title = (resource.get("title") or title)

        record["document_index"].append({
            "doc_id": doc_id,
            "doc_type": doc_type,
            "title": title,
            "encounter_id": None,
            "authored_at": timestamp,
            "signed_at": resource.get("date") if rtype == "Composition" else None,
            "author": {"id": None, "name": author, "role": None},
            "organization": {"service": None, "center": None},
            "language": resource.get("language") or "es",
            "status": resource.get("status") or "unknown",
            "raw_text": None,
            "attachments": [],
            "source_refs": [src_id],
        })

        if rtype == "Encounter":
            reason = ((resource.get("reasonCode") or [{}])[0] or {}).get("text")
            encounter_id = _new_id("enc")
            enc_obj = {
                "id": encounter_id,
                "type": _encounter_type(resource),
                "start": (resource.get("period") or {}).get("start"),
                "end": (resource.get("period") or {}).get("end"),
                "reason_text": reason,
                "service": ((resource.get("serviceType") or {}).get("text")),
                "disposition": "unknown",
                "diagnosis_ids": [],
                "procedure_ids": [],
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            }
            ev = _add_evidence(record, doc_id=doc_id, quote=reason or "Episodio asistencial", section="encounter")
            enc_obj["evidence_ids"].append(ev)
            record["encounters"].append(enc_obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="encounter",
                text=f"{reason or 'Motivo no informado'} | estado: {resource.get('status') or 's/d'}",
                date=timestamp,
                author=author,
                codes=[],
                source_section="episodios_asistenciales",
                resource_type=rtype,
            )

        elif rtype == "Condition":
            code = _codeable(resource.get("code") or {})
            clinical = ((resource.get("clinicalStatus") or {}).get("coding") or [{}])[0]
            verification = ((resource.get("verificationStatus") or {}).get("coding") or [{}])[0]
            dx_obj = {
                "id": _new_id("dx"),
                "clinical_status": clinical.get("code") or "unknown",
                "verification_status": verification.get("code") or "confirmed",
                "code": code,
                "onset_date": _resource_date(resource),
                "abatement_date": None,
                "category": "problem-list-item",
                "severity": None,
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("clinicalStatus", {}).get("text") or "unknown",
                "asserted_at": timestamp,
            }
            quote = f"{code.get('display')} ({code.get('value') or 'sin código'})"
            ev = _add_evidence(record, doc_id=doc_id, quote=quote, section="condition")
            dx_obj["evidence_ids"].append(ev)
            record["diagnoses"].append(dx_obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="problem",
                text=quote,
                date=timestamp,
                author=author,
                codes=[code],
                source_section="problemas_diagnosticos",
                resource_type=rtype,
            )

        elif rtype == "Procedure":
            code = _codeable(resource.get("code") or {})
            category_text = _norm((resource.get("category") or {}).get("text"))
            is_surgery = any(x in category_text for x in ["cirug", "quir", "surgery"]) or "cirug" in _norm(code.get("display"))
            proc_obj = {
                "id": _new_id("proc"),
                "code": code,
                "description": code.get("display"),
                "performed_date": _resource_date(resource),
                "body_site": None,
                "outcome": None,
                "is_surgery": is_surgery,
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            }
            ev = _add_evidence(record, doc_id=doc_id, quote=code.get("display") or "Procedimiento", section="procedure")
            proc_obj["evidence_ids"].append(ev)
            record["procedures"].append(proc_obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="procedure",
                text=code.get("display") or "Procedimiento",
                date=timestamp,
                author=author,
                codes=[code],
                source_section="procedimientos",
                resource_type=rtype,
            )

        elif rtype == "MedicationRequest":
            med = _codeable(resource.get("medicationCodeableConcept") or {})
            dosage = ((resource.get("dosageInstruction") or [{}])[0] or {}).get("text")
            med_obj = {
                "id": _new_id("med"),
                "status": resource.get("status") or "unknown",
                "type": "chronic",
                "drug": {
                    "system": med.get("system"),
                    "code": med.get("value"),
                    "display": med.get("display"),
                },
                "dose_text": dosage,
                "route": None,
                "frequency_text": dosage,
                "start_date": _resource_date(resource),
                "end_date": None,
                "indication_dx_ids": [],
                "source_refs": [src_id],
                "evidence_ids": [],
                "asserted_at": timestamp,
            }
            quote = f"{med.get('display')} | {dosage or 'sin posología'}"
            ev = _add_evidence(record, doc_id=doc_id, quote=quote, section="medication")
            med_obj["evidence_ids"].append(ev)
            record["medications"].append(med_obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="medication",
                text=quote,
                date=timestamp,
                author=author,
                codes=[med],
                source_section="medicacion",
                resource_type=rtype,
            )

        elif rtype == "AllergyIntolerance":
            agent = _codeable(resource.get("code") or {})
            reaction = ((resource.get("reaction") or [{}])[0] or {})
            manifest = (((reaction.get("manifestation") or [{}])[0] or {}).get("coding") or [{}])[0]
            alg_obj = {
                "id": _new_id("alg"),
                "type": "allergy",
                "clinical_status": resource.get("clinicalStatus", {}).get("text") or "active",
                "verification_status": resource.get("verificationStatus", {}).get("text") or "confirmed",
                "criticality": resource.get("criticality") or "unknown",
                "agent": {
                    "system": agent.get("system"),
                    "value": agent.get("value"),
                    "display": agent.get("display"),
                },
                "reaction": manifest.get("display") or reaction.get("description"),
                "severity": reaction.get("severity"),
                "onset_date": _resource_date(resource),
                "recorded_date": _resource_date(resource),
                "source_refs": [src_id],
                "evidence_ids": [],
                "asserted_at": timestamp,
            }
            quote = f"{agent.get('display')} | criticidad {alg_obj['criticality']} | {alg_obj.get('reaction') or 'sin reacción'}"
            ev = _add_evidence(record, doc_id=doc_id, quote=quote, section="allergy")
            alg_obj["evidence_ids"].append(ev)
            record["allergies_adrs"].append(alg_obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="allergy",
                text=quote,
                date=timestamp,
                author=author,
                codes=[agent],
                source_section="alergias_ram",
                resource_type=rtype,
            )

        elif rtype == "DiagnosticReport":
            cat = _norm((((resource.get("category") or [{}])[0] or {}).get("text")))
            code = _codeable(resource.get("code") or {})
            conclusion = resource.get("conclusion") or code.get("display")
            if "lab" in cat or "laborat" in cat:
                obj = {
                    "id": _new_id("lab"),
                    "panel": code.get("display"),
                    "test": {"system": code.get("system"), "code": code.get("value"), "display": code.get("display")},
                    "value": None,
                    "unit": None,
                    "reference_range": None,
                    "interpretation": "unknown",
                    "collected_at": (resource.get("effectiveDateTime") or timestamp),
                    "reported_at": (resource.get("issued") or timestamp),
                    "source_refs": [src_id],
                    "evidence_ids": [],
                    "status": resource.get("status") or "unknown",
                    "asserted_at": timestamp,
                }
                ev = _add_evidence(record, doc_id=doc_id, quote=conclusion or "Resultado laboratorio", section="lab")
                obj["evidence_ids"].append(ev)
                record["lab_results"].append(obj)
                _add_section_fragment(
                    record,
                    doc_id=doc_id,
                    section_type="lab",
                    text=conclusion or "Resultado de laboratorio",
                    date=timestamp,
                    author=author,
                    codes=[code],
                    source_section="laboratorio",
                    resource_type=rtype,
                )
            elif "imag" in cat or "radiolog" in cat:
                obj = {
                    "id": _new_id("img"),
                    "modality": "other",
                    "study_date": _resource_date(resource),
                    "body_site": None,
                    "findings": conclusion,
                    "impression": conclusion,
                    "source_refs": [src_id],
                    "evidence_ids": [],
                    "status": resource.get("status") or "unknown",
                    "asserted_at": timestamp,
                }
                ev = _add_evidence(record, doc_id=doc_id, quote=conclusion or "Informe de imagen", section="imaging")
                obj["evidence_ids"].append(ev)
                record["imaging_reports"].append(obj)
                _add_section_fragment(
                    record,
                    doc_id=doc_id,
                    section_type="imaging",
                    text=conclusion or "Informe de imagen",
                    date=timestamp,
                    author=author,
                    codes=[code],
                    source_section="pruebas_imagen",
                    resource_type=rtype,
                )
            else:
                obj = {
                    "id": _new_id("odt"),
                    "test_type": "other",
                    "test_date": _resource_date(resource),
                    "result_text": conclusion,
                    "conclusion": conclusion,
                    "source_refs": [src_id],
                    "evidence_ids": [],
                    "status": resource.get("status") or "unknown",
                    "asserted_at": timestamp,
                }
                ev = _add_evidence(record, doc_id=doc_id, quote=conclusion or "Otra prueba diagnóstica", section="other-test")
                obj["evidence_ids"].append(ev)
                record["other_diagnostic_tests"].append(obj)
                _add_section_fragment(
                    record,
                    doc_id=doc_id,
                    section_type="other",
                    text=conclusion or "Otra prueba diagnóstica",
                    date=timestamp,
                    author=author,
                    codes=[code],
                    source_section="informes_pruebas",
                    resource_type=rtype,
                )

        elif rtype == "Observation":
            code = _codeable(resource.get("code") or {})
            value = resource.get("valueQuantity") or {}
            text = resource.get("valueString") or (
                f"{value.get('value', '')} {value.get('unit', '')}".strip()
                if value else code.get("display")
            )
            obj = {
                "id": _new_id("lab"),
                "panel": None,
                "test": {"system": code.get("system"), "code": code.get("value"), "display": code.get("display")},
                "value": value.get("value") if value else text,
                "unit": value.get("unit") if value else None,
                "reference_range": None,
                "interpretation": "unknown",
                "collected_at": resource.get("effectiveDateTime") or timestamp,
                "reported_at": resource.get("issued") or timestamp,
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            }
            ev = _add_evidence(record, doc_id=doc_id, quote=f"{code.get('display')}: {text}", section="observation")
            obj["evidence_ids"].append(ev)
            record["lab_results"].append(obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="lab",
                text=f"{code.get('display')}: {text}",
                date=timestamp,
                author=author,
                codes=[code],
                source_section="pruebas_observaciones",
                resource_type=rtype,
            )

        elif rtype == "CarePlan":
            text = (resource.get("description") or resource.get("title") or "Plan de cuidados")
            obj = {
                "id": _new_id("nur"),
                "diagnosis": None,
                "interventions": [text],
                "outcomes": [],
                "care_recommendations": text,
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            }
            ev = _add_evidence(record, doc_id=doc_id, quote=text, section="nursing")
            obj["evidence_ids"].append(ev)
            record["nursing_care"].append(obj)
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="nursing",
                text=text,
                date=timestamp,
                author=author,
                codes=[],
                source_section="planes_cuidados",
                resource_type=rtype,
            )

        elif rtype == "Composition":
            title = resource.get("title") or "Informe clínico"
            text = ((resource.get("text") or {}).get("div") or "").replace("<div>", "").replace("</div>", "")
            summary = {
                "id": _new_id("dis"),
                "encounter_id": None,
                "admission_date": None,
                "discharge_date": _resource_date(resource),
                "main_diagnosis_id": None,
                "secondary_diagnosis_ids": [],
                "procedures_ids": [],
                "treatment_at_discharge": None,
                "recommendations": title,
                "follow_up": None,
                "source_refs": [src_id],
                "evidence_ids": [],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            }
            ev = _add_evidence(record, doc_id=doc_id, quote=(text or title), section="composition")
            summary["evidence_ids"].append(ev)
            record["discharge_summaries"].append(summary)
            record["clinical_notes"].append({
                "id": _new_id("note"),
                "note_type": "discharge",
                "encounter_id": None,
                "authored_at": timestamp,
                "author": {"name": author, "role": None},
                "text": text or title,
                "source_refs": [src_id],
                "status": resource.get("status") or "unknown",
                "asserted_at": timestamp,
            })
            _add_section_fragment(
                record,
                doc_id=doc_id,
                section_type="discharge",
                text=text or title,
                date=timestamp,
                author=author,
                codes=[],
                source_section="informes_alta_evolucion",
                resource_type=rtype,
            )

        elif rtype == "DocumentReference":
            contents = resource.get("content") or []
            for content_idx, content in enumerate(contents):
                att = (content or {}).get("attachment") or {}
                ctype = att.get("contentType") or "application/octet-stream"
                title = att.get("title") or f"adjunto_{content_idx + 1}"
                data_b64 = att.get("data")
                text_snippet = None
                if isinstance(data_b64, str) and data_b64:
                    try:
                        raw = base64.b64decode(data_b64, validate=False)
                        if ctype.startswith("text/") or ctype in {"application/json", "application/xml"}:
                            text_snippet = raw.decode("utf-8", errors="replace")[:500]
                    except Exception:
                        text_snippet = None

                attachment_id = _new_id("att")
                record["attachments"].append({
                    "id": attachment_id,
                    "doc_id": doc_id,
                    "mime_type": ctype,
                    "file_name": title,
                    "sha256": None,
                    "storage_uri": att.get("url") or f"inline-base64://{source_id}/{content_idx}",
                    "pages": None,
                    "ocr_applied": False,
                    "extracted_text": text_snippet,
                })

                for d in record["document_index"]:
                    if d["doc_id"] == doc_id:
                        d["attachments"].append(attachment_id)
                        if text_snippet:
                            d["raw_text"] = text_snippet
                        break

                display_text = text_snippet or f"{title} ({ctype})"
                ev = _add_evidence(record, doc_id=doc_id, quote=display_text, section="attachment")
                access = {
                    "content_type": ctype,
                    "title": title,
                    "url": f"/fhir/pacientes/{cip}/documentos/{idx}/{content_idx}",
                }
                _add_section_fragment(
                    record,
                    doc_id=doc_id,
                    section_type="document",
                    text=display_text,
                    date=timestamp,
                    author=author,
                    codes=[],
                    source_section="informes_documentos",
                    resource_type=rtype,
                    manual_review=not bool(text_snippet),
                    confidence=0.92 if text_snippet else 0.78,
                    document_access=access,
                )
                record["clinical_notes"].append({
                    "id": _new_id("note"),
                    "note_type": "document-reference",
                    "encounter_id": None,
                    "authored_at": timestamp,
                    "author": {"name": author, "role": None},
                    "text": display_text,
                    "source_refs": [src_id],
                    "evidence_ids": [ev],
                    "status": resource.get("status") or "unknown",
                    "asserted_at": timestamp,
                })

    _resolve_diagnosis_conflicts(record)
    _resolve_medication_conflicts(record)
    _resolve_allergy_conflicts(record)

    record["document_index"].sort(key=lambda x: x.get("authored_at") or "", reverse=True)
    record["all_sections"].sort(key=lambda x: x.get("date") or "", reverse=True)

    return record


def validate_master_record_for_demo(record: dict) -> dict:
    """
    Checklist de calidad para demos E2E con pacientes sintéticos.
    """
    checks = []

    def add_check(cid: str, title: str, ok: bool, detail: str, severity: str = "high") -> None:
        checks.append({
            "id": cid,
            "title": title,
            "status": "pass" if ok else ("warn" if severity == "medium" else "fail"),
            "severity": severity,
            "detail": detail,
        })

    pd = record.get("patient_demographics", {})
    add_check(
        "demographics_min",
        "Demográficos mínimos",
        bool(pd.get("patient_id") and pd.get("birth_date") and pd.get("sex_at_birth")),
        "Se requieren patient_id, birth_date y sex_at_birth.",
    )

    add_check(
        "traceability_min",
        "Trazabilidad mínima",
        len(record.get("source_refs", [])) > 0 and len(record.get("evidence_spans", [])) > 0,
        "Debe existir source_refs y evidence_spans para auditoría.",
    )

    doc_types = {d.get("doc_type") for d in record.get("document_index", []) if d.get("doc_type")}
    covered = sorted([d for d in REQUIRED_HCDSNS_DOC_TYPES if d in doc_types])
    add_check(
        "hcdsns_blocks",
        "Cobertura documental HCDSNS/RD1093",
        len(covered) >= 6,
        f"Cubiertos {len(covered)}/9 bloques: {', '.join(covered) if covered else 'ninguno'}.",
        severity="medium",
    )

    add_check(
        "clinical_min",
        "Mínimo clínico para demo",
        bool(record.get("encounters") and (record.get("clinical_notes") or record.get("discharge_summaries"))),
        "Se recomienda >=1 encounter y >=1 nota o alta para flujo completo.",
    )

    add_check(
        "search_ready",
        "Índice all_sections listo",
        len(record.get("all_sections", [])) >= 8,
        "Se recomiendan al menos 8 fragmentos para búsquedas híbridas útiles.",
        severity="medium",
    )

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    score = max(0, 100 - (len(fails) * 25) - (len(warns) * 10))

    return {
        "passes": len(fails) == 0,
        "score": score,
        "checks": checks,
        "summary": {
            "fail_count": len(fails),
            "warn_count": len(warns),
            "required_doc_types": REQUIRED_HCDSNS_DOC_TYPES,
            "present_doc_types": sorted(doc_types),
        },
    }


def to_legacy_history_view(record: dict, cip: str) -> dict:
    """
    Vista compatible con dashboard actual, derivada del PMR.
    """
    p = record.get("patient_demographics", {})
    nombre = f"{p.get('name') or ''} {p.get('family_name_1') or ''}".strip() or "Paciente"

    problemas = []
    for dx in record.get("diagnoses", []):
        code = dx.get("code") or {}
        problemas.append({
            "estado": dx.get("clinical_status"),
            "fecha_inicio": dx.get("onset_date"),
            "codigo": code.get("value"),
            "sistema_codigo": code.get("system"),
            "descripcion": code.get("display"),
        })

    tratamiento = []
    for med in record.get("medications", []):
        drug = med.get("drug") or {}
        tratamiento.append({
            "estado": med.get("status"),
            "medicamento": drug.get("display"),
            "codigo": drug.get("code"),
            "sistema_codigo": drug.get("system"),
            "posologia": med.get("dose_text") or med.get("frequency_text"),
        })

    alergias = []
    for alg in record.get("allergies_adrs", []):
        agent = alg.get("agent") or {}
        alergias.append({
            "criticidad": alg.get("criticality"),
            "sustancia": agent.get("display"),
            "codigo": agent.get("value"),
            "sistema_codigo": agent.get("system"),
            "manifestacion": alg.get("reaction"),
        })

    episodios = []
    for enc in record.get("encounters", []):
        episodios.append({
            "estado": enc.get("status"),
            "fecha": (enc.get("start") or "")[:10] if enc.get("start") else None,
            "motivo": enc.get("reason_text"),
            "resultado": enc.get("disposition"),
        })

    all_sections = []
    for sec in record.get("all_sections", []):
        all_sections.append({
            "source_section": sec.get("source_section") or sec.get("section_type"),
            "resource_type": sec.get("resource_type") or sec.get("section_type"),
            "timestamp": sec.get("date"),
            "author": sec.get("author") or "No informado",
            "text": sec.get("text"),
            "confidence": sec.get("confidence", 0.75),
            "manual_review": sec.get("manual_review", False),
            "document_access": sec.get("document_access"),
        })

    catalog = []
    playbook = extraction_playbook()
    for rtype, rules in playbook.items():
        section_name = rules["targets"][0]
        catalog.append({
            "section": section_name,
            "resources": [rtype],
        })

    return {
        "estructura": "HCIS",
        "paciente": {
            "nombre_completo": nombre,
            "cip": p.get("cip_sns") or cip,
            "fecha_nacimiento": p.get("birth_date"),
            "sexo": p.get("sex_at_birth"),
        },
        "problemas": problemas,
        "tratamiento": tratamiento,
        "alergias": alergias,
        "episodios": episodios,
        "all_sections": all_sections,
        "catalogo_hcis": catalog,
        "master_record": record,
        "quality_report": validate_master_record_for_demo(record),
    }
