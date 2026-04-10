"""
Generador de pacientes sintéticos en formato FHIR R4 con documentos clínicos.

Objetivo:
- Simular historial longitudinal realista tipo HCIS/HCDSNS.
- Incluir recursos estructurados + documentos adjuntos (PDF/texto) para
  probar ingesta all-sections, extracción de evidencia y búsquedas híbridas.

Uso:
    python generate_patients.py
"""

import base64
import json
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "patients")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _b64_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _build_fake_pdf_bytes(lines: list[str]) -> bytes:
    safe_lines = [l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:110] for l in lines]
    stream_lines = ["BT", "/F1 10 Tf", "40 790 Td"]
    first = True
    y = 790
    for line in safe_lines:
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

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj",
    ]

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

    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii"))
    return bytes(pdf)


def _b64_pdf(lines: list[str]) -> str:
    return base64.b64encode(_build_fake_pdf_bytes(lines)).decode("ascii")


def make_bundle(resources):
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": r} for r in resources],
    }


def patient(pid, cip, name, surname, birth_date, gender):
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [{"system": "https://www.sermas.es/cip", "value": cip}],
        "name": [{"family": surname, "given": [name]}],
        "birthDate": birth_date,
        "gender": gender,
        "telecom": [{"system": "phone", "value": "+34600000000"}],
        "address": [{"city": "Madrid", "country": "ES", "postalCode": "28001"}],
    }


def condition(pid, code, display, onset_date, clinical_status="active"):
    return {
        "resourceType": "Condition",
        "id": f"cond-{pid}-{code}",
        "subject": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
        "onsetDateTime": onset_date,
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": clinical_status}]
        },
        "recordedDate": onset_date,
    }


def medication(pid, code, display, dose, frequency, authored_on):
    return {
        "resourceType": "MedicationRequest",
        "id": f"med-{pid}-{code}-{authored_on}",
        "subject": {"reference": f"Patient/{pid}"},
        "status": "active",
        "authoredOn": authored_on,
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": code, "display": display}]
        },
        "dosageInstruction": [{"text": f"{dose} - {frequency}"}],
    }


def allergy(pid, code, display, severity, manifestation, recorded_date):
    return {
        "resourceType": "AllergyIntolerance",
        "id": f"alg-{pid}-{code}",
        "patient": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
        "criticality": severity,
        "recordedDate": recorded_date,
        "reaction": [{"manifestation": [{"coding": [{"display": manifestation}]}]}],
    }


def encounter(pid, enc_id, date_str, reason, diagnosis, class_code="AMB", service_text="Consulta externa"):
    return {
        "resourceType": "Encounter",
        "id": enc_id,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "finished",
        "class": {"code": class_code},
        "serviceType": {"text": service_text},
        "period": {"start": date_str},
        "reasonCode": [{"text": reason}],
        "diagnosis": [{"condition": {"display": diagnosis}}],
    }


def procedure(pid, proc_id, code, display, date_str, category_text="Cirugía"):
    return {
        "resourceType": "Procedure",
        "id": proc_id,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "completed",
        "performedDateTime": date_str,
        "category": {"text": category_text},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
    }


def diagnostic_report(pid, rid, category_text, code, display, conclusion, effective_date, issued_date):
    return {
        "resourceType": "DiagnosticReport",
        "id": rid,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "final",
        "category": [{"text": category_text}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
        "conclusion": conclusion,
        "effectiveDateTime": effective_date,
        "issued": issued_date,
    }


def observation(pid, oid, code, display, value, unit, effective_date):
    return {
        "resourceType": "Observation",
        "id": oid,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
        "valueQuantity": {"value": value, "unit": unit},
        "effectiveDateTime": effective_date,
    }


def care_plan(pid, cid, title, date_str):
    return {
        "resourceType": "CarePlan",
        "id": cid,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "active",
        "created": date_str,
        "title": title,
        "description": title,
    }


def composition(pid, cid, title, doc_type_text, date_str, body_text):
    return {
        "resourceType": "Composition",
        "id": cid,
        "subject": {"reference": f"Patient/{pid}"},
        "status": "final",
        "type": {"text": doc_type_text},
        "title": title,
        "date": date_str,
        "text": {"status": "generated", "div": f"<div>{body_text}</div>"},
    }


def document_reference(pid, did, title, doc_type_text, created_date, attachment_content_type, attachment_b64):
    return {
        "resourceType": "DocumentReference",
        "id": did,
        "status": "current",
        "subject": {"reference": f"Patient/{pid}"},
        "date": created_date,
        "type": {"text": doc_type_text},
        "content": [{
            "attachment": {
                "contentType": attachment_content_type,
                "title": title,
                "creation": created_date,
                "data": attachment_b64,
            }
        }],
    }


def build_common_docs(pid, profile_label):
    text_doc = document_reference(
        pid,
        f"doc-{pid}-txt",
        f"Nota evolutiva {profile_label}",
        "Historia clínica resumida",
        "2026-04-01T09:00:00Z",
        "text/plain",
        _b64_text(f"Resumen clínico longitudinal del paciente {pid}. Riesgos y antecedentes relevantes."),
    )
    pdf_doc = document_reference(
        pid,
        f"doc-{pid}-pdf",
        f"Informe de urgencias {profile_label}",
        "Urgencias",
        "2026-04-02T10:30:00Z",
        "application/pdf",
        _b64_pdf([
            f"Informe de urgencias - {profile_label}",
            "Motivo de consulta: dolor torácico/disnea según perfil",
            "Pruebas realizadas: ECG, analítica y Rx",
            "Plan: seguimiento por su médico responsable",
        ]),
    )
    return [text_doc, pdf_doc]


PATIENTS = [
    {
        "patient": patient("P001", "2800001234", "Carlos", "Martínez López", "1966-03-14", "male"),
        "conditions": [
            condition("P001", "38341003", "Hipertensión arterial", "2015-06-01"),
            condition("P001", "44054006", "Diabetes mellitus tipo 2", "2018-01-20"),
            condition("P001", "53741008", "Cardiopatía isquémica", "2021-11-05"),
        ],
        "medications": [
            medication("P001", "29046", "Losartán 50mg", "1 comprimido", "1 vez al día", "2026-02-01"),
            medication("P001", "860975", "Metformina 850mg", "1 comprimido", "2 veces al día", "2026-02-01"),
            medication("P001", "308460", "Atorvastatina 40mg", "1 comprimido", "por la noche", "2026-02-01"),
        ],
        "allergies": [],
        "encounters": [
            encounter("P001", "enc-p001-1", "2026-01-22T10:00:00Z", "Urgencias por dolor torácico", "Angina estable", "EMER", "Urgencias"),
            encounter("P001", "enc-p001-2", "2026-02-11T09:30:00Z", "Control de atención primaria", "Ajuste antihipertensivo", "AMB", "Atención primaria"),
            encounter("P001", "enc-p001-3", "2026-03-10T12:00:00Z", "Revisión consulta externa cardiología", "Cardiopatía estable", "AMB", "Consulta externa"),
        ],
        "procedures": [
            procedure("P001", "proc-p001-1", "232717009", "Angioplastia coronaria previa", "2023-02-14", "Cirugía cardiaca")
        ],
        "reports": [
            diagnostic_report("P001", "rep-p001-lab", "Laboratorio", "718-7", "Hemoglobina", "Hemoglobina 13.1 g/dL", "2026-03-10T08:00:00Z", "2026-03-10T11:00:00Z"),
            diagnostic_report("P001", "rep-p001-img", "Radiología e imagen", "30746-2", "Radiografía de tórax", "Sin infiltrados agudos", "2026-01-22T10:15:00Z", "2026-01-22T11:20:00Z"),
            diagnostic_report("P001", "rep-p001-ecg", "Electrocardiograma", "131328", "ECG 12 derivaciones", "Ritmo sinusal, sin cambios agudos", "2026-01-22T10:10:00Z", "2026-01-22T10:40:00Z"),
        ],
        "observations": [
            observation("P001", "obs-p001-1", "8480-6", "Presión arterial sistólica", 152, "mmHg", "2026-01-22T10:00:00Z")
        ],
        "careplans": [
            care_plan("P001", "care-p001-1", "Plan de cuidados de enfermería cardiovascular", "2026-03-10")
        ],
        "compositions": [
            composition("P001", "comp-p001-hcr", "Historia clínica resumida", "Resumen", "2026-03-11T09:00:00Z", "Antecedentes cardiovasculares relevantes y control metabólico."),
            composition("P001", "comp-p001-alta", "Informe clínico de alta", "Alta hospitalaria", "2026-01-23T12:00:00Z", "Alta tras dolor torácico sin criterios de isquemia aguda."),
        ],
        "documents": build_common_docs("P001", "Cardio"),
    },
    {
        "patient": patient("P002", "2800005678", "Ana", "García Ruiz", "1989-07-22", "female"),
        "conditions": [
            condition("P002", "195967001", "Asma bronquial", "2005-03-10"),
            condition("P002", "21719001", "Rinitis alérgica", "2007-09-15"),
        ],
        "medications": [
            medication("P002", "1049510", "Salbutamol inhalador", "2 pulsaciones", "si precisa", "2026-02-11"),
            medication("P002", "1552099", "Budesonida/Formoterol", "1 pulsación", "2 veces al día", "2026-02-11"),
        ],
        "allergies": [
            allergy("P002", "372687004", "Ibuprofeno", "high", "Broncoespasmo grave", "2024-09-01"),
            allergy("P002", "372687004", "Aspirina", "high", "Urticaria generalizada", "2024-09-01"),
        ],
        "encounters": [
            encounter("P002", "enc-p002-1", "2026-02-01T21:00:00Z", "Urgencias por disnea", "Crisis asmática", "EMER", "Urgencias"),
            encounter("P002", "enc-p002-2", "2026-02-11T10:00:00Z", "Revisión consulta externa neumología", "Asma controlada", "AMB", "Consulta externa"),
            encounter("P002", "enc-p002-3", "2026-03-01T09:00:00Z", "Atención primaria seguimiento asma", "Mantener tratamiento", "AMB", "Atención primaria"),
        ],
        "procedures": [],
        "reports": [
            diagnostic_report("P002", "rep-p002-lab", "Laboratorio", "26499-4", "Leucocitos", "Leucocitos 8.5 x10e9/L", "2026-02-01T20:40:00Z", "2026-02-01T22:00:00Z"),
            diagnostic_report("P002", "rep-p002-img", "Radiología e imagen", "30746-2", "Rx tórax", "Sin consolidaciones", "2026-02-01T20:50:00Z", "2026-02-01T21:40:00Z"),
            diagnostic_report("P002", "rep-p002-spi", "Espirometría", "19868-9", "Espirometría", "Patrón obstructivo leve", "2026-02-11T10:10:00Z", "2026-02-11T11:00:00Z"),
        ],
        "observations": [
            observation("P002", "obs-p002-1", "59408-5", "Saturación O2", 95, "%", "2026-02-01T21:00:00Z")
        ],
        "careplans": [
            care_plan("P002", "care-p002-1", "Plan de educación inhaladores", "2026-02-12")
        ],
        "compositions": [
            composition("P002", "comp-p002-hcr", "Historia clínica resumida", "Resumen", "2026-03-01T09:20:00Z", "Paciente asmática con RAM a AINEs."),
            composition("P002", "comp-p002-alta", "Informe clínico de alta", "Alta urgencias", "2026-02-02T08:00:00Z", "Alta tras resolución de broncoespasmo en urgencias."),
        ],
        "documents": build_common_docs("P002", "Neumo"),
    },
    {
        "patient": patient("P003", "2800009012", "Carmen", "Fernández Iglesias", "1948-11-30", "female"),
        "conditions": [
            condition("P003", "38341003", "Hipertensión arterial", "2000-04-01"),
            condition("P003", "40425004", "Fibrilación auricular", "2019-03-22"),
            condition("P003", "396275006", "Osteoporosis", "2020-06-05"),
        ],
        "medications": [
            medication("P003", "11289", "Warfarina 5mg", "según INR", "1 vez al día", "2026-03-01"),
            medication("P003", "114194", "Bisoprolol 5mg", "1 comprimido", "1 vez al día", "2026-03-01"),
        ],
        "allergies": [
            allergy("P003", "91936005", "Penicilina", "low", "Exantema cutáneo", "2018-01-04")
        ],
        "encounters": [
            encounter("P003", "enc-p003-1", "2026-03-05T10:30:00Z", "Urgencias por mareo", "Hipotensión ortostática", "EMER", "Urgencias"),
            encounter("P003", "enc-p003-2", "2026-03-08T10:00:00Z", "Consulta externa medicina interna", "Revisión de tratamiento", "AMB", "Consulta externa"),
            encounter("P003", "enc-p003-3", "2026-03-12T09:00:00Z", "Atención primaria control INR", "INR en rango", "AMB", "Atención primaria"),
        ],
        "procedures": [
            procedure("P003", "proc-p003-1", "80146002", "Artroplastia de cadera previa", "2021-10-10", "Cirugía ortopédica")
        ],
        "reports": [
            diagnostic_report("P003", "rep-p003-lab", "Laboratorio", "34714-6", "INR", "INR 2.8 en rango terapéutico", "2026-03-12T08:00:00Z", "2026-03-12T10:30:00Z"),
            diagnostic_report("P003", "rep-p003-img", "Radiología e imagen", "36643-5", "TAC craneal", "Sin hallazgos agudos", "2026-03-05T11:00:00Z", "2026-03-05T12:00:00Z"),
            diagnostic_report("P003", "rep-p003-ecg", "Electrocardiograma", "131328", "ECG", "FA conocida sin cambios", "2026-03-05T11:10:00Z", "2026-03-05T11:30:00Z"),
        ],
        "observations": [
            observation("P003", "obs-p003-1", "8462-4", "Presión arterial diastólica", 58, "mmHg", "2026-03-05T10:25:00Z")
        ],
        "careplans": [
            care_plan("P003", "care-p003-1", "Plan prevención caídas", "2026-03-12")
        ],
        "compositions": [
            composition("P003", "comp-p003-hcr", "Historia clínica resumida", "Resumen", "2026-03-12T09:20:00Z", "Paciente pluripatológica con polimedicación y control estrecho."),
            composition("P003", "comp-p003-alta", "Informe clínico de alta", "Alta urgencias", "2026-03-05T14:00:00Z", "Alta con ajuste de antihipertensivos por hipotensión ortostática."),
        ],
        "documents": build_common_docs("P003", "Interna"),
    },
]


def main():
    for p in PATIENTS:
        resources = []
        resources.append(p["patient"])
        resources.extend(p["conditions"])
        resources.extend(p["medications"])
        resources.extend(p["allergies"])
        resources.extend(p["encounters"])
        resources.extend(p["procedures"])
        resources.extend(p["reports"])
        resources.extend(p["observations"])
        resources.extend(p["careplans"])
        resources.extend(p["compositions"])
        resources.extend(p["documents"])

        bundle = make_bundle(resources)
        cip = p["patient"]["identifier"][0]["value"]
        out_path = os.path.join(OUTPUT_DIR, f"{cip}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)

        print(f"Generado: {cip} - {p['patient']['name'][0]['given'][0]} {p['patient']['name'][0]['family']} ({len(resources)} recursos)")

    print(f"\n{len(PATIENTS)} pacientes guardados en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
