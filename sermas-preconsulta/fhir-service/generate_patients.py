"""
Generador de pacientes sintéticos en formato FHIR R4.

Crea 5 pacientes con perfiles clínicos variados y realistas para demostrar
el sistema de triaje. Cada paciente tiene un CIP ficticio, diagnósticos,
medicación y alergias.

Los ficheros se guardan en data/patients/{CIP}.json.

Uso:
    python generate_patients.py
"""

import json
import os
from datetime import date

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "patients")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def make_bundle(patient, conditions, medications, allergies, encounters):
    """Construye un FHIR R4 Bundle con todos los recursos del paciente."""
    pid = patient["id"]
    entries = [{"resource": patient}]
    entries += [{"resource": c} for c in conditions]
    entries += [{"resource": m} for m in medications]
    entries += [{"resource": a} for a in allergies]
    entries += [{"resource": e} for e in encounters]

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries,
    }


def patient(pid, cip, name, surname, birth_date, gender):
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [
            {"system": "https://www.sermas.es/cip", "value": cip}
        ],
        "name": [{"family": surname, "given": [name]}],
        "birthDate": birth_date,
        "gender": gender,
        "address": [{"city": "Madrid", "country": "ES"}],
    }


def condition(pid, code, display, onset_date, clinical_status="active"):
    return {
        "resourceType": "Condition",
        "subject": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
        "onsetDateTime": onset_date,
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": clinical_status}]
        },
    }


def medication(pid, code, display, dose, frequency):
    return {
        "resourceType": "MedicationRequest",
        "subject": {"reference": f"Patient/{pid}"},
        "status": "active",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": code, "display": display}]
        },
        "dosageInstruction": [{"text": f"{dose} — {frequency}"}],
    }


def allergy(pid, code, display, severity, manifestation):
    return {
        "resourceType": "AllergyIntolerance",
        "patient": {"reference": f"Patient/{pid}"},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
        "criticality": severity,
        "reaction": [{"manifestation": [{"coding": [{"display": manifestation}]}]}],
    }


def encounter(pid, date_str, reason, diagnosis):
    return {
        "resourceType": "Encounter",
        "subject": {"reference": f"Patient/{pid}"},
        "status": "finished",
        "period": {"start": date_str},
        "reasonCode": [{"text": reason}],
        "diagnosis": [{"condition": {"display": diagnosis}}],
    }


# ─────────────────────────────────────────────────────────────────────────────
# PACIENTES
# Diseñados para que cada uno produzca un triaje diferente al cruzar síntomas.
# ─────────────────────────────────────────────────────────────────────────────

PATIENTS = [
    # ── Paciente 1: Riesgo cardiovascular alto ───────────────────────────────
    # Llama por dolor de pecho → briefing debe alertar al médico urgentemente
    {
        "patient": patient("P001", "2800001234", "Carlos", "Martínez López", "1966-03-14", "male"),
        "conditions": [
            condition("P001", "38341003", "Hipertensión arterial", "2015-06-01"),
            condition("P001", "44054006", "Diabetes mellitus tipo 2", "2018-01-20"),
            condition("P001", "53741008", "Cardiopatía isquémica", "2021-11-05"),
        ],
        "medications": [
            medication("P001", "29046", "Losartán 50mg", "1 comprimido", "1 vez al día"),
            medication("P001", "860975", "Metformina 850mg", "1 comprimido", "2 veces al día"),
            medication("P001", "308460", "Atorvastatina 40mg", "1 comprimido", "por la noche"),
            medication("P001", "1191", "Aspirina 100mg", "1 comprimido", "1 vez al día"),
        ],
        "allergies": [],
        "encounters": [
            encounter("P001", "2025-11-10", "Revisión cardiología", "Cardiopatía isquémica estable"),
            encounter("P001", "2026-01-22", "Dolor torácico", "Angina de pecho, ajuste de medicación"),
        ],
    },
    # ── Paciente 2: Alergia grave + asma ─────────────────────────────────────
    # Llama por dificultad para respirar → cruce con alergias es crítico
    {
        "patient": patient("P002", "2800005678", "Ana", "García Ruiz", "1989-07-22", "female"),
        "conditions": [
            condition("P002", "195967001", "Asma bronquial", "2005-03-10"),
            condition("P002", "21719001", "Rinitis alérgica", "2007-09-15"),
        ],
        "medications": [
            medication("P002", "1049510", "Salbutamol 100mcg inhalador", "2 pulsaciones", "si precisa"),
            medication("P002", "1552099", "Budesonida/Formoterol 160/4.5mcg", "1 pulsación", "2 veces al día"),
            medication("P002", "1085793", "Montelukast 10mg", "1 comprimido", "por la noche"),
        ],
        "allergies": [
            allergy("P002", "372687004", "Ibuprofeno (AINE)", "high",
                    "Broncoespasmo grave — ingreso UCI 2019"),
            allergy("P002", "372687004", "Aspirina", "high",
                    "Urticaria generalizada"),
        ],
        "encounters": [
            encounter("P002", "2025-08-03", "Crisis asmática", "Asma moderada, nebulización en urgencias"),
            encounter("P002", "2026-02-11", "Revisión neumología", "Asma bien controlada, continuar tratamiento"),
        ],
    },
    # ── Paciente 3: Anciana polimedicada ─────────────────────────────────────
    # Llama por mareos → importante revisar interacciones medicamentosas
    {
        "patient": patient("P003", "2800009012", "Carmen", "Fernández Iglesias", "1948-11-30", "female"),
        "conditions": [
            condition("P003", "38341003", "Hipertensión arterial", "2000-04-01"),
            condition("P003", "44054006", "Diabetes mellitus tipo 2", "2010-07-15"),
            condition("P003", "40425004", "Fibrilación auricular", "2019-03-22"),
            condition("P003", "73211009", "Hipotiroidismo", "2012-01-10"),
            condition("P003", "396275006", "Osteoporosis", "2020-06-05"),
        ],
        "medications": [
            medication("P003", "29046", "Losartán 100mg", "1 comprimido", "1 vez al día"),
            medication("P003", "114194", "Bisoprolol 5mg", "1 comprimido", "1 vez al día"),
            medication("P003", "11289", "Warfarina 5mg", "según INR", "1 vez al día"),
            medication("P003", "10582", "Levotiroxina 75mcg", "1 comprimido", "en ayunas"),
            medication("P003", "860975", "Metformina 500mg", "1 comprimido", "2 veces al día"),
            medication("P003", "41493", "Alendronato 70mg", "1 comprimido", "semanal en ayunas"),
        ],
        "allergies": [
            allergy("P003", "372687004", "Penicilina", "low", "Exantema cutáneo leve"),
        ],
        "encounters": [
            encounter("P003", "2025-12-01", "Control INR", "INR 2.8 — en rango terapéutico"),
            encounter("P003", "2026-03-05", "Mareo episódico", "Hipotensión ortostática, revisar dosis antihipertensivos"),
        ],
    },
    # ── Paciente 4: Joven sin antecedentes ───────────────────────────────────
    # Llama por fiebre alta y dolor de garganta → triaje bajo, cita rutinaria
    {
        "patient": patient("P004", "2800003456", "Miguel", "Torres Vega", "1998-04-05", "male"),
        "conditions": [],
        "medications": [],
        "allergies": [],
        "encounters": [
            encounter("P004", "2025-01-15", "Revisión general", "Paciente sano, analítica normal"),
        ],
    },
    # ── Paciente 5: Embarazada con hipertensión gestacional ──────────────────
    # Llama por dolor de cabeza fuerte + visión borrosa → alerta preeclampsia
    {
        "patient": patient("P005", "2800007890", "Laura", "Sánchez Moreno", "1993-09-18", "female"),
        "conditions": [
            condition("P005", "48194001", "Hipertensión gestacional", "2026-02-15"),
            condition("P005", "72892002", "Embarazo normal (semana 32)", "2025-11-01"),
        ],
        "medications": [
            medication("P005", "29046", "Labetalol 100mg", "1 comprimido", "2 veces al día"),
            medication("P005", "66857006", "Ácido fólico 5mg", "1 comprimido", "1 vez al día"),
        ],
        "allergies": [],
        "encounters": [
            encounter("P005", "2026-03-20", "Control obstétrico", "TA 145/95, proteinuria leve, control estrecho"),
            encounter("P005", "2026-04-01", "Urgencias obstétricas", "TA 155/100, ingreso observación 24h"),
        ],
    },
]


def main():
    for p in PATIENTS:
        bundle = make_bundle(
            p["patient"],
            p["conditions"],
            p["medications"],
            p["allergies"],
            p["encounters"],
        )
        cip = p["patient"]["identifier"][0]["value"]
        out_path = os.path.join(OUTPUT_DIR, f"{cip}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        print(f"Generado: {cip} — {p['patient']['name'][0]['given'][0]} {p['patient']['name'][0]['family']}")

    print(f"\n{len(PATIENTS)} pacientes guardados en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()