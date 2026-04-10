"""
Prueba del triaje con datos sintéticos.

El formato de síntomas es el que llega desde el voice-agent (visible en el dashboard).
El historial es mock hasta que el fhir-service lo implemente.

Uso:
    cd sermas-preconsulta/llm-service
    python tests/test_triage.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from triage import generate_triage


# ── Síntomas — formato real de SymptomSummary.model_dump() del voice-agent ───
# severity: "mild" | "moderate" | "severe"  (no numérico)
# relevant_history_flags: banderas detectadas por el agente en conversación
# raw_transcript: turnos completos (no se usa en triage pero llega en el payload)
SYMPTOMS_ALTA = {
    "cip": "ABCD1234567",
    "chief_complaint": "Dolor torácico opresivo con sudoración",
    "symptoms": ["dolor en el pecho", "sudoración fría", "falta de aire"],
    "duration": "2 horas",
    "severity": "severe",
    "associated_symptoms": ["mareo", "náuseas", "dolor en el brazo izquierdo"],
    "relevant_history_flags": ["hipertensión", "toma AAS"],
    "raw_transcript": [],
}

SYMPTOMS_MEDIA = {
    "cip": "WXYZ9876543",
    "chief_complaint": "Fiebre alta desde ayer",
    "symptoms": ["fiebre", "dolor de cabeza", "tos seca"],
    "duration": "24 horas",
    "severity": "moderate",
    "associated_symptoms": ["escalofríos", "cansancio"],
    "relevant_history_flags": [],
    "raw_transcript": [],
}

SYMPTOMS_BAJA = {
    "cip": "EFGH5554433",
    "chief_complaint": "Revisión de tensión arterial",
    "symptoms": ["leve dolor de cabeza"],
    "duration": "esta mañana",
    "severity": "mild",
    "associated_symptoms": [],
    "relevant_history_flags": ["hipertensión conocida"],
    "raw_transcript": [],
}


# ── Historial mock — formato esperado por triage.py ───────────────────────────
# (hasta que fhir-service lo rellene con datos Synthea reales)
HISTORY_CARDIACO = {
    "paciente": {
        "nombre": "Antonio García Ruiz",
        "edad": 62,
        "sexo": "Hombre",
    },
    "diagnosticos_activos": [
        {"nombre": "Hipertensión esencial"},
        {"nombre": "Diabetes mellitus tipo 2"},
        {"nombre": "Hiperlipidemia"},
    ],
    "medicacion_actual": [
        {"nombre": "Enalapril 10 mg"},
        {"nombre": "Metformina 850 mg"},
        {"nombre": "Atorvastatina 20 mg"},
        {"nombre": "AAS 100 mg"},
    ],
    "alergias": [
        {"sustancia": "Penicilina", "manifestacion": "urticaria"},
    ],
    "visitas_recientes": [
        {"fecha": "2025-11-14", "motivo": "Control rutinario HTA/DM · TA 145/90 · HbA1c 7.2%"},
    ],
}

HISTORY_VACIO = {
    "paciente": {
        "nombre": "María López Martín",
        "edad": 34,
        "sexo": "Mujer",
    },
    "diagnosticos_activos": [],
    "medicacion_actual": [],
    "alergias": [],
    "visitas_recientes": [],
}


# ── Runner ────────────────────────────────────────────────────────────────────
CASOS = [
    ("Caso 1 — Urgencia ALTA esperada (dolor torácico + cardiopatía)", SYMPTOMS_ALTA, HISTORY_CARDIACO),
    ("Caso 2 — Urgencia MEDIA esperada (fiebre, sin historial)", SYMPTOMS_MEDIA, HISTORY_VACIO),
    ("Caso 3 — Urgencia BAJA esperada (revisión rutinaria)", SYMPTOMS_BAJA, HISTORY_CARDIACO),
]


async def main():
    for titulo, symptoms, history in CASOS:
        print(f"\n{'='*70}")
        print(f"  {titulo}")
        print("="*70)
        result = await generate_triage(symptoms, history)
        print(f"  Urgencia     : {result['urgencia'].upper()}")
        print(f"  Resumen      : {result['resumen']}")
        alertas = result.get("alertas", [])
        if alertas:
            print(f"  Alertas      : {' | '.join(alertas)}")
        print(f"  Recomendación: {result['recomendacion']}")


if __name__ == "__main__":
    asyncio.run(main())
