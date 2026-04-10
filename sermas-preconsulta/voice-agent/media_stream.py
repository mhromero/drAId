"""
Manejador de Twilio Media Streams (WebSocket bidireccional).

Protocolo de audio:
  - Entrada (Twilio → nosotros): mulaw 8kHz mono, chunks de ~20ms en base64
  - Salida (nosotros → Twilio): mulaw 8kHz mono en base64

Flujo por turno:
  1. Recibir chunks de audio del paciente
  2. VAD simple por energía RMS → detectar fin de frase
  3. Enviar buffer acumulado a Whisper (STT)
  4. Enviar transcripción al VoiceAgent (GPT-4o)
  5. Sintetizar respuesta con OpenAI TTS → mulaw
  6. Enviar audio de vuelta por el WebSocket
"""

import asyncio
import audioop
import base64
import json
import os

import httpx
from fastapi import WebSocket

from agent import VoiceAgent
from stt import transcribe_audio
from tts import synthesize_speech_mulaw

# --- Parámetros de VAD (Voice Activity Detection) ---
SILENCE_RMS_THRESHOLD = 200   # Por debajo de este RMS = silencio
SILENCE_DURATION_S = 1.5      # Segundos de silencio para considerar fin de turno
CHUNK_DURATION_MS = 20        # Twilio envía chunks de 20ms
SILENCE_CHUNKS_NEEDED = int(SILENCE_DURATION_S * 1000 / CHUNK_DURATION_MS)  # 75 chunks


async def handle_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    stream_sid: str | None = None
    agent: VoiceAgent | None = None

    audio_buffer = bytearray()
    silence_chunks = 0
    is_speaking = False
    # Flag para no procesar audio mientras el agente "habla" (evita eco)
    agent_speaking = False

    try:
        async for raw_message in websocket.iter_text():
            data = json.loads(raw_message)
            event = data.get("event")

            if event == "connected":
                continue

            elif event == "start":
                stream_sid = data["streamSid"]
                call_sid = data["start"]["callSid"]

                agent = VoiceAgent(session_id=call_sid)
                greeting_audio = await synthesize_speech_mulaw(agent.get_greeting())

                agent_speaking = True
                await _send_audio(websocket, stream_sid, greeting_audio)
                agent_speaking = False

            elif event == "media":
                if agent is None or agent_speaking:
                    continue

                track = data["media"].get("track", "inbound")
                if track != "inbound":
                    continue

                payload = base64.b64decode(data["media"]["payload"])
                pcm = audioop.ulaw2lin(payload, 2)
                rms = audioop.rms(pcm, 2)

                if rms > SILENCE_RMS_THRESHOLD:
                    is_speaking = True
                    silence_chunks = 0
                    audio_buffer.extend(payload)

                elif is_speaking:
                    # El paciente acaba de callarse — seguimos acumulando hasta el umbral
                    silence_chunks += 1
                    audio_buffer.extend(payload)

                    if silence_chunks >= SILENCE_CHUNKS_NEEDED:
                        is_speaking = False
                        captured = bytes(audio_buffer)
                        audio_buffer.clear()
                        silence_chunks = 0

                        # Procesar turno de forma asíncrona para no bloquear el WebSocket
                        asyncio.create_task(
                            _process_turn(websocket, stream_sid, agent, captured)
                        )

            elif event == "stop":
                break

    except Exception as exc:
        print(f"[media_stream] Error inesperado: {exc}")

    finally:
        if agent and not agent.is_done():
            # Sesión interrumpida sin completarse — intentar enviar lo que tenemos
            await _post_to_fhir_service(agent)


async def _process_turn(
    websocket: WebSocket,
    stream_sid: str,
    agent: VoiceAgent,
    audio_bytes: bytes,
) -> None:
    """STT → LLM → TTS → enviar audio. Se ejecuta como tarea asyncio."""
    transcript = await transcribe_audio(audio_bytes)

    if not transcript:
        return

    result = await agent.process_turn(transcript)

    response_audio = await synthesize_speech_mulaw(result["response"])
    await _send_audio(websocket, stream_sid, response_audio)

    if result["done"]:
        await _post_to_fhir_service(agent)
        await websocket.close()


async def _send_audio(websocket: WebSocket, stream_sid: str, mulaw_bytes: bytes) -> None:
    """Envía audio mulaw a Twilio por el WebSocket."""
    payload = base64.b64encode(mulaw_bytes).decode("utf-8")
    await websocket.send_text(
        json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload},
        })
    )


async def _post_to_fhir_service(agent: VoiceAgent) -> None:
    """
    Envía el resumen de síntomas al fhir-service vía HTTP POST (Opción A — síncrono).

    TODO [PRODUCCIÓN]: Reemplazar esta llamada directa por publicación en una cola
    asíncrona (Redis Streams / RabbitMQ) para garantizar entrega aunque el
    fhir-service esté caído. Ejemplo con Redis:

        await redis.xadd(
            "preconsulta:symptoms",
            {
                "session_id": agent.session_id,
                "payload": agent.get_summary().model_dump_json(),
            }
        )

    El fhir-service actuaría como consumer del stream y procesaría los mensajes
    con reintentos automáticos (XACK / XPENDING).
    """
    fhir_url = os.getenv("FHIR_SERVICE_URL", "http://fhir-service:8001")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{fhir_url}/fhir/preconsulta",
                json={
                    "session_id": agent.session_id,
                    "cip": agent.symptoms.cip,
                    "symptoms": agent.symptoms.model_dump(),
                },
            )
    except httpx.RequestError as exc:
        # TODO [PRODUCCIÓN]: si falla, encolar para reintento automático
        print(
            f"[WARN] fhir-service no disponible (session={agent.session_id}): {exc}. "
            "En producción: encolar en Redis Streams para garantizar entrega."
        )