"""
SERMAS Pre-Consulta — Voice Agent
FastAPI app: recibe llamadas de Twilio y abre un Media Stream WebSocket.

Endpoints:
  POST /voice/incoming   — Twilio llama aquí al recibir una llamada entrante.
                           Devuelve TwiML que conecta la llamada a nuestro WebSocket.
  WS   /voice/stream     — Canal de audio bidireccional con Twilio Media Streams.
  GET  /health           — Health check para Docker/K8s.
"""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import Response

from media_stream import handle_media_stream
from fastapi import WebSocket

load_dotenv()

app = FastAPI(
    title="SERMAS Pre-Consulta — Voice Agent",
    version="0.1.0",
)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-agent"}


@app.post("/voice/incoming")
async def incoming_call(request: Request):
    """
    Twilio llama a este endpoint cuando el paciente marca el 900 102 112.
    Devolvemos TwiML con <Connect><Stream> para abrir el WebSocket de audio.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    # Twilio necesita wss:// para el WebSocket en producción.
    # En local con ngrok: ngrok expone HTTPS/WSS automáticamente.
    ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/voice/stream">
            <Parameter name="call_sid" value="{call_sid}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """
    WebSocket de Twilio Media Streams.
    Delega todo el procesamiento a media_stream.handle_media_stream().
    """
    await handle_media_stream(websocket)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )