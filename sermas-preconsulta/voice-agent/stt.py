import io
import wave
import audioop
from openai import AsyncOpenAI

client = AsyncOpenAI()

SAMPLE_RATE = 8000  # Twilio envía mulaw a 8kHz


def mulaw_to_wav(mulaw_bytes: bytes) -> bytes:
    """Convierte audio mulaw 8kHz (formato Twilio) a WAV PCM 16-bit para Whisper."""
    pcm_data = audioop.ulaw2lin(mulaw_bytes, 2)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_data)

    return buffer.getvalue()


async def transcribe_audio(mulaw_bytes: bytes) -> str:
    """
    Transcribe audio mulaw usando OpenAI Whisper.
    El prompt de contexto mejora el reconocimiento de términos médicos y el CIP.
    """
    wav_bytes = mulaw_to_wav(mulaw_bytes)

    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"

    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="es",
        prompt=(
            "Servicio de citas SERMAS Madrid. "
            "CIP, código de identificación personal, tarjeta sanitaria, "
            "síntomas, dolor, fiebre, consulta médica, cita previa."
        ),
    )

    return response.text.strip()