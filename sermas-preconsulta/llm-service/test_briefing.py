"""
Prueba manual del briefing con datos sintéticos.

Uso:
    1. ollama serve  (en otra terminal)
    2. ollama pull llama3.1:8b
    3. cd sermas-preconsulta/llm-service
    4. python test_briefing.py
"""

import asyncio
from briefing import generate_briefing


SAMPLE_SYMPTOMS = {
    "cip": "ABCD1234567",
    "chief_complaint": "Dolor torácico opresivo",
    "symptoms": ["dolor en el pecho", "sudoración", "falta de aire"],
    "duration": "unas 2 horas",
    "severity": "7/10",
    "associated_symptoms": ["mareo leve", "náuseas"],
}

SAMPLE_FHIR_HISTORY = {
    "patient": {
        "id": "patient-001",
        "age": 62,
        "gender": "male",
    },
    "conditions": [
        {"code": "I10", "display": "Hipertensión esencial", "onset": "2015"},
        {"code": "E11", "display": "Diabetes mellitus tipo 2", "onset": "2018"},
        {"code": "E78.5", "display": "Hiperlipidemia", "onset": "2019"},
    ],
    "medications": [
        {"name": "Enalapril 10 mg", "frequency": "1-0-0"},
        {"name": "Metformina 850 mg", "frequency": "1-0-1"},
        {"name": "Atorvastatina 20 mg", "frequency": "0-0-1"},
    ],
    "allergies": [{"substance": "Penicilina", "reaction": "urticaria"}],
    "last_visit": {
        "date": "2025-11-14",
        "reason": "Control rutinario HTA/DM",
        "notes": "TA 145/90, HbA1c 7.2%",
    },
}


async def main():
    print(">>> Enviando a Ollama llama3.1:8b...\n")
    briefing = await generate_briefing(SAMPLE_SYMPTOMS, SAMPLE_FHIR_HISTORY)
    print("=" * 70)
    print("BRIEFING GENERADO")
    print("=" * 70)
    print(briefing)
    print("=" * 70)
    print(f"\nLongitud: {len(briefing.split())} palabras")


if __name__ == "__main__":
    asyncio.run(main())
