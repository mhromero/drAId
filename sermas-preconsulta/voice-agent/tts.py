"""
TTS — Text To Speech

PROTOTIPO (gratuito): gTTS (Google TTS sin API key, voz robótica pero funcional en español).
PRODUCCIÓN SERMAS:    descomentar el bloque OpenAI TTS y comentar el bloque gTTS.
                      Sin cambios en la firma de synthesize_speech_mulaw().

Nota: ambas opciones devuelven mulaw 8kHz mono — el único formato
que acepta Twilio Media Streams por WebSocket.
"""

import io
import audioop
from pydub import AudioSegment

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCCIÓN: OpenAI TTS (voz 'nova', español natural)
# Requiere OPENAI_API_KEY. Coste: $15/1M caracteres (~céntimos por llamada).
# ─────────────────────────────────────────────────────────────────────────────
# from openai import AsyncOpenAI
# _openai_client = AsyncOpenAI()
#
# async def synthesize_speech_mulaw(text: str) -> bytes:
#     response = await _openai_client.audio.speech.create(
#         model="tts-1",
#         voice="nova",
#         input=text,
#         response_format="mp3",
#     )
#     mp3_bytes = response.content
#     audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
#     audio = audio.set_channels(1).set_frame_rate(8000).set_sample_width(2)
#     return audioop.lin2ulaw(audio.raw_data, 2)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# PROTOTIPO: gTTS (Google Text-to-Speech, gratuito, sin API key)
# Requiere conexión a internet. Voz más robótica pero inteligible en español.
# Pipeline: texto → MP3 (gTTS) → PCM 8kHz mono (pydub) → mulaw (audioop)
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
from gtts import gTTS


def _synthesize_sync(text: str) -> bytes:
    """Genera MP3 con gTTS de forma síncrona."""
    tts = gTTS(text=text, lang="es", slow=False)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


async def synthesize_speech_mulaw(text: str) -> bytes:
    """
    Convierte texto a voz (gTTS) y devuelve audio mulaw 8kHz para Twilio Media Streams.
    gTTS hace una petición HTTP a Google — se ejecuta en executor para no bloquear.
    """
    loop = asyncio.get_event_loop()
    mp3_bytes = await loop.run_in_executor(None, _synthesize_sync, text)

    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_channels(1).set_frame_rate(8000).set_sample_width(2)

    return audioop.lin2ulaw(audio.raw_data, 2)