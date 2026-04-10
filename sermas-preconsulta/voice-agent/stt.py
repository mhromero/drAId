"""
STT — Speech To Text

PROTOTIPO (gratuito): faster-whisper corriendo en local (CPU, modelo 'small').
PRODUCCIÓN SERMAS:    descomentar el bloque OpenAI Whisper API y comentar el bloque
                      faster-whisper. Sin cambios en la firma de transcribe_audio().
"""

import asyncio
import io
import wave
import audioop
import os
import tempfile

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCCIÓN: OpenAI Whisper API
# Requiere OPENAI_API_KEY. Coste: $0.006/min de audio.
# ─────────────────────────────────────────────────────────────────────────────
# from openai import AsyncOpenAI
# _openai_client = AsyncOpenAI()
#
# async def transcribe_audio(mulaw_bytes: bytes) -> str:
#     wav_bytes = _mulaw_to_wav(mulaw_bytes)
#     audio_file = io.BytesIO(wav_bytes)
#     audio_file.name = "audio.wav"
#     response = await _openai_client.audio.transcriptions.create(
#         model="whisper-1",
#         file=audio_file,
#         language="es",
#         prompt=(
#             "Servicio de citas SERMAS Madrid. "
#             "CIP, código de identificación personal, tarjeta sanitaria, "
#             "síntomas, dolor, fiebre, consulta médica, cita previa."
#         ),
#     )
#     return response.text.strip()
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# PROTOTIPO: faster-whisper local (sin coste, corre en CPU)
# Modelos disponibles por orden de calidad/velocidad: tiny · base · small · medium
# 'small' + int8 es el equilibrio óptimo para CPU en una demo.
# ─────────────────────────────────────────────────────────────────────────────
from faster_whisper import WhisperModel

_WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
_whisper_model = WhisperModel(_WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

SAMPLE_RATE = 8000  # Twilio envía mulaw a 8kHz


def _mulaw_to_wav(mulaw_bytes: bytes) -> bytes:
    """Convierte audio mulaw 8kHz (Twilio) a WAV PCM 16-bit para Whisper."""
    pcm_data = audioop.ulaw2lin(mulaw_bytes, 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _transcribe_sync(wav_path: str) -> str:
    """Llama a faster-whisper de forma síncrona (se ejecuta en un executor)."""
    segments, _ = _whisper_model.transcribe(
        wav_path,
        language="es",
        beam_size=5,
        initial_prompt=(
            "Servicio de citas SERMAS Madrid. "
            "CIP, tarjeta sanitaria, síntomas, dolor, fiebre, consulta médica."
        ),
    )
    return " ".join(s.text for s in segments).strip()


async def transcribe_audio(mulaw_bytes: bytes) -> str:
    """
    Transcribe audio mulaw usando faster-whisper en local.
    Ejecuta la inferencia en un ThreadPoolExecutor para no bloquear el event loop.
    """
    wav_bytes = _mulaw_to_wav(mulaw_bytes)

    # faster-whisper necesita ruta de fichero, no BytesIO
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(None, _transcribe_sync, tmp_path)
    finally:
        os.unlink(tmp_path)

    return transcript
