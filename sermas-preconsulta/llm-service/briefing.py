"""
Generación del briefing clínico pre-consulta.

Combina los síntomas recogidos por el voice-agent con el historial FHIR
del paciente y pide a un LLM local (Ollama llama3.1:8b) que redacte un
párrafo-resumen para el médico.
"""

import json
import os
from openai import AsyncOpenAI


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("LLM_BRIEFING_MODEL", "llama3.1:8b")

_client = AsyncOpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)


SYSTEM_PROMPT = """Eres un asistente clínico que prepara briefings pre-consulta
para médicos de atención primaria del SERMAS.

Tu tarea: leer los síntomas que ha recogido el agente telefónico y el historial
FHIR del paciente, y redactar un ÚNICO PÁRRAFO (máx. 150 palabras) en español
clínico, neutro y conciso, que el médico pueda leer en 20 segundos antes de
entrar a consulta.

El párrafo debe incluir, cuando la información esté disponible:
- Motivo de consulta y síntoma principal.
- Duración, intensidad y síntomas asociados.
- Antecedentes relevantes del historial (patologías crónicas, alergias,
  medicación activa) que puedan estar relacionados con el cuadro actual.
- Banderas rojas si las hubiera.

Reglas estrictas:
- No inventes datos. Si un campo falta, omítelo.
- No hagas diagnóstico ni propongas tratamiento.
- No uses listas ni encabezados: solo prosa corrida.
- No incluyas saludos, despedidas ni meta-comentarios.
"""


def _build_user_message(symptoms: dict, fhir_history: dict) -> str:
    return (
        "SÍNTOMAS RECOGIDOS POR EL AGENTE:\n"
        f"{json.dumps(symptoms, ensure_ascii=False, indent=2)}\n\n"
        "HISTORIAL FHIR DEL PACIENTE:\n"
        f"{json.dumps(fhir_history, ensure_ascii=False, indent=2)}\n\n"
        "Redacta el párrafo-resumen para el médico."
    )


async def generate_briefing(symptoms: dict, fhir_history: dict) -> str:
    response = await _client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(symptoms, fhir_history)},
        ],
        temperature=0.2,
        max_tokens=350,
    )
    return response.choices[0].message.content.strip()
