import io
import audioop
from openai import AsyncOpenAI
from pydub import AudioSegment

client = AsyncOpenAI()


async def synthesize_speech_mulaw(text: str) -> bytes:
    """
    Convierte texto a voz con OpenAI TTS (voz 'nova', español natural)
    y devuelve audio en mulaw 8kHz mono — el único formato que acepta Twilio Media Streams.

    Pipeline: texto → MP3 24kHz (OpenAI) → PCM 8kHz mono (pydub) → mulaw (audioop)
    """
    response = await client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        response_format="mp3",
    )

    mp3_bytes = response.content

    # Resamplear a 8kHz mono 16-bit (requisito Twilio)
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_channels(1).set_frame_rate(8000).set_sample_width(2)

    mulaw_bytes = audioop.lin2ulaw(audio.raw_data, 2)
    return mulaw_bytes