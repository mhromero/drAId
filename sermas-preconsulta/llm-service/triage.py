"""
Generador de triaje clínico usando LLM.

Recibe síntomas recogidos por el voice-agent + historial FHIR mapeado
y devuelve un triaje estructurado para el médico.

Usa el mismo patrón de backends que el voice-agent:
LLM_BACKEND=ollama | groq | openai
"""

import json
import os
import re
from openai import AsyncOpenAI

_BACKEND = os.getenv("LLM_BACKEND", "ollama")
_CONFIGS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "api_key": "ollama",
               "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b")},
    "groq":   {"base_url": "https://api.groq.com/openai/v1",
               "api_key": os.getenv("GROQ_API_KEY", ""), "model": "llama-3.1-8b-instant"},
    "openai": {"base_url": None, "api_key": os.getenv("OPENAI_API_KEY", ""), "model": "gpt-4o"},
}
_cfg = _CONFIGS[_BACKEND]
# api_key="ollama" cuando el backend es local — el SDK lo requiere pero no lo usa
_client = AsyncOpenAI(
    api_key=_cfg["api_key"] or "not-needed",
    base_url=_cfg["base_url"],
)

TRIAGE_PROMPT = """Eres un asistente clínico de triaje para el SERMAS.
Recibirás los síntomas referidos por un paciente en una llamada telefónica y su historial clínico.
Tu tarea es ayudar al médico a priorizar si debe contactar al paciente antes de la cita.

IMPORTANTE:
- No haces diagnósticos. El médico toma la decisión final.
- Sé conciso. El médico tiene poco tiempo.
- Detecta alertas de seguridad: alergias relevantes, interacciones con medicación actual, condiciones de riesgo.
- El nivel de urgencia es: "alta" (contactar hoy), "media" (valorar en 24-48h), "baja" (mantener cita).

Responde ÚNICAMENTE con este JSON, sin texto adicional:
{
  "urgencia": "alta|media|baja",
  "resumen": "2-3 frases para el médico sobre el motivo y contexto clínico",
  "alertas": ["alerta 1 si existe", "alerta 2 si existe"],
  "recomendacion": "una frase con la acción sugerida"
}"""


async def generate_triage(symptoms: dict, history: dict) -> dict:
    """Genera triaje clínico combinando síntomas + historial FHIR."""

    paciente = history.get("paciente", {})
    nombre = paciente.get("nombre", "Paciente desconocido")
    edad = paciente.get("edad", "?")
    sexo = paciente.get("sexo", "")
    diagnosticos = [d["nombre"] for d in history.get("diagnosticos_activos", [])]
    medicacion = [m["nombre"] for m in history.get("medicacion_actual", [])]
    alergias = [f"{a['sustancia']} ({a['manifestacion']})" for a in history.get("alergias", [])]
    visitas = history.get("visitas_recientes", [])
    ultima_visita = f"{visitas[0]['fecha']}: {visitas[0]['motivo']}" if visitas else "Sin visitas recientes"

    user_content = f"""PACIENTE: {nombre}, {edad} años, {sexo}

SÍNTOMAS REFERIDOS EN LA LLAMADA:
- Motivo principal: {symptoms.get('chief_complaint', 'No especificado')}
- Síntomas: {', '.join(symptoms.get('symptoms', []))}
- Duración: {symptoms.get('duration', 'No especificada')}
- Severidad: {symptoms.get('severity', 'No especificada')}
- Síntomas asociados: {', '.join(symptoms.get('associated_symptoms', []))}

HISTORIAL CLÍNICO:
- Diagnósticos activos: {', '.join(diagnosticos) if diagnosticos else 'Ninguno'}
- Medicación actual: {', '.join(medicacion) if medicacion else 'Ninguna'}
- Alergias: {', '.join(alergias) if alergias else 'Ninguna conocida'}
- Última visita: {ultima_visita}"""

    response = await _client.chat.completions.create(
        model=_cfg["model"],
        messages=[
            {"role": "system", "content": TRIAGE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=400,
    )

    raw = response.choices[0].message.content.strip()
    return _parse_triage(raw)


def _parse_triage(raw: str) -> dict:
    """Extrae el JSON del response, con fallback si el LLM no respeta el formato."""
    # Intentar extraer bloque JSON aunque haya texto alrededor
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            # Validar campos obligatorios
            if "urgencia" in data and data["urgencia"] in ("alta", "media", "baja"):
                data.setdefault("alertas", [])
                data.setdefault("resumen", "")
                data.setdefault("recomendacion", "")
                return data
        except json.JSONDecodeError:
            pass

    # Fallback si el LLM no devuelve JSON válido
    return {
        "urgencia": "media",
        "resumen": raw[:300] if raw else "No se pudo generar triaje.",
        "alertas": [],
        "recomendacion": "Valorar contacto con el paciente.",
    }