#!/usr/bin/env python3
"""
Simulación de llamada completa — SERMAS Pre-Consulta

Emula una llamada telefónica end-to-end sin necesidad de Twilio ni micrófono:
  1. Inicia una sesión con el VoiceAgent
  2. Simula turnos de conversación (paciente ficticio)
  3. El agente extrae síntomas y los envía al fhir-service
  4. El fhir-service cruza con el historial FHIR y llama al llm-service
  5. El triaje aparece en el dashboard (http://localhost:8001)

Uso:
    cd sermas-preconsulta
    python simulate_call.py [--paciente carlos|ana|carmen|miguel|laura]

Servicios necesarios (en terminales separadas o con docker-compose):
    cd fhir-service  && LLM_SERVICE_URL=http://localhost:8002 uvicorn main:app --port 8001
    cd llm-service   && LLM_BACKEND=ollama uvicorn main:app --port 8002
"""

import argparse
import asyncio
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "voice-agent"))

from agent import VoiceAgent

FHIR_SERVICE_URL = os.getenv("FHIR_SERVICE_URL", "http://localhost:8001")

# ── Guiones de conversación por paciente ─────────────────────────────────────
SCENARIOS = {
    "carlos": {
        "cip": "2800001234",
        "phone": "+34600000001",
        "turns": [
            "Mi CIP es 2800001234",
            "Tengo un dolor de pecho muy fuerte, como una presión",
            "Lleva unas dos horas, es un ocho sobre diez",
            "También me suda mucho y noto el brazo izquierdo raro, entumecido",
            "No, nada más. ¿Es grave?",
            "Sí, eso es todo, gracias",
        ],
    },
    "ana": {
        "cip": "2800005678",
        "phone": "+34600000002",
        "turns": [
            "Mi CIP es 2800005678",
            "Tengo dificultad para respirar, como pitidos en el pecho",
            "Empezó esta mañana, puede ser un cinco o seis",
            "Ayer tomé un ibuprofeno por un dolor de cabeza",
            "Sí, eso es todo",
        ],
    },
    "carmen": {
        "cip": "2800009012",
        "phone": "+34600000003",
        "turns": [
            "Mi CIP es 2800009012",
            "Tengo mareos cuando me levanto, llevo así tres días",
            "No es muy fuerte, como un tres. Pero me da miedo caerme",
            "No tengo náuseas ni me he desmayado",
            "Tomo muchos medicamentos, la warfarina entre otros",
            "Sí, eso es todo",
        ],
    },
    "miguel": {
        "cip": "2800003456",
        "phone": "+34600000004",
        "turns": [
            "Mi CIP es 2800003456",
            "Me duele la garganta y tengo fiebre desde hace dos días",
            "La fiebre es de 38 y medio, el dolor de garganta un cuatro",
            "Malestar general pero nada más, no me cuesta respirar",
            "Sí, eso es todo",
        ],
    },
    "laura": {
        "cip": "2800007890",
        "phone": "+34600000005",
        "turns": [
            "Mi CIP es 2800007890",
            "Tengo un dolor de cabeza muy fuerte desde esta mañana",
            "Es un ocho, nunca me había dolido tanto. Y veo un poco borroso",
            "Estoy embarazada, en la semana 32",
            "No, solo eso, pero me preocupa mucho",
            "Sí",
        ],
    },
}


async def simulate(paciente: str):
    scenario = SCENARIOS.get(paciente)
    if not scenario:
        print(f"Paciente desconocido: {paciente}. Opciones: {list(SCENARIOS.keys())}")
        return

    print(f"\n{'='*60}")
    print(f"  SIMULACIÓN — Paciente: {paciente.upper()} (CIP {scenario['cip']})")
    print(f"{'='*60}\n")

    agent = VoiceAgent(session_id=f"sim-{paciente}-001")

    # Saludo inicial
    greeting = agent.get_greeting()
    print(f"[AGENTE] {greeting}\n")

    # Turnos de conversación
    for user_msg in scenario["turns"]:
        print(f"[PACIENTE] {user_msg}")
        result = await agent.process_turn(user_msg)
        print(f"[AGENTE]   {result['response']}\n")

        if result["done"]:
            print("─" * 60)
            print("  Conversación completada. Enviando al fhir-service...")
            print("─" * 60)
            await post_to_fhir(agent, scenario)
            break
    else:
        # El agente no terminó en los turnos previstos — forzar envío
        print("\n[SIM] Turnos agotados sin completar. Enviando datos parciales...")
        await post_to_fhir(agent, scenario)


async def post_to_fhir(agent: VoiceAgent, scenario: dict):
    symptoms = agent.get_summary().model_dump(exclude={"raw_transcript"})

    payload = {
        "session_id": agent.session_id,
        "cip": scenario["cip"],
        "caller_phone": scenario["phone"],
        "symptoms": symptoms,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{FHIR_SERVICE_URL}/fhir/preconsulta", json=payload)
            case = r.json()

        triage = case.get("triage", {})
        paciente = case.get("history", {}).get("paciente", {})
        print(f"\n  Paciente:    {paciente.get('nombre', '?')}, {paciente.get('edad', '?')} años")
        print(f"  Urgencia:    {triage.get('urgencia', '?').upper()}")
        print(f"  Resumen:     {triage.get('resumen', '?')}")
        alertas = triage.get("alertas", [])
        if alertas:
            print(f"  Alertas:     {' | '.join(alertas)}")
        print(f"  Recomend.:   {triage.get('recomendacion', '?')}")
        print(f"\n  Dashboard:   http://localhost:8001")

    except httpx.RequestError as e:
        print(f"\n[ERROR] No se pudo conectar al fhir-service: {e}")
        print("  ¿Están arrancados el fhir-service y el llm-service?")
        print("  Ver README o ejecutar: docker-compose up")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simular llamada SERMAS Pre-Consulta")
    parser.add_argument(
        "--paciente",
        choices=list(SCENARIOS.keys()),
        default="carlos",
        help="Perfil del paciente a simular (default: carlos)",
    )
    args = parser.parse_args()

    os.environ.setdefault("LLM_BACKEND", "ollama")
    os.environ.setdefault("OLLAMA_MODEL", "llama3.1:8b")
    os.environ.setdefault("OPENAI_API_KEY", "not-needed")

    asyncio.run(simulate(args.paciente))