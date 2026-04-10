# TODO — SERMAS Pre-Consulta

## voice-agent

- [ ] **Cola asíncrona para envío al fhir-service** (`media_stream.py:_post_to_fhir_service`)
  Reemplazar la llamada HTTP directa por Redis Streams / RabbitMQ para garantizar
  entrega aunque el fhir-service esté caído. Ver comentario con ejemplo en el código.

- [ ] **Cambiar LLM a GPT-4o** (`agent.py`)
  En producción SERMAS usar `gpt-4o` (mayor precisión clínica).
  Cambiar `LLM_BACKEND=openai` en `.env` y añadir `OPENAI_API_KEY`.

- [ ] **Cambiar STT a OpenAI Whisper API** (`stt.py`)
  Descomentar el bloque OpenAI y comentar el bloque faster-whisper.
  Mayor precisión y sin coste de CPU en producción.

- [ ] **Cambiar TTS a OpenAI TTS** (`tts.py`)
  Descomentar el bloque OpenAI (voz `nova`) y comentar el bloque gTTS.
  Voz más natural para el paciente.

- [ ] **VAD mejorado** (`media_stream.py`)
  El VAD actual es por energía RMS simple. En producción usar
  `webrtcvad` o `silero-vad` para detección de silencio más robusta
  (reduce cortes prematuros y falsos positivos).

- [ ] **Gestión de sesiones persistente**
  Las sesiones están en memoria (`dict` en `media_stream.py`).
  En producción usar Redis para sobrevivir reinicios y escalar horizontalmente.

- [ ] **Probar con Twilio + ngrok**
  Configurar número Twilio, apuntar webhook a ngrok, test de llamada real.
  Credenciales necesarias: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `BASE_URL`.

## fhir-service

- [ ] **Integración con HSIC y ORUS (producción)**
  `fhir_client.py` tiene dos modos: `local` (Synthea, prototipo) y `fhir` (servidor real).
  En producción: `FHIR_MODE=fhir` + `FHIR_SERVER_URL=https://fhir.sermas.madrid.es`.
  - HSIC expone Patient, Condition, MedicationRequest, AllergyIntolerance, Encounter en FHIR R4.
  - ORUS gestiona citas (Appointment) — se puede usar para crear/modificar citas post-triaje.
  - Requiere autenticación OAuth2 con el IdP del SERMAS y acuerdo de integración formal.

## llm-service

- [ ] **Implementar briefing.py**
  Prompt clínico estructurado: síntomas recogidos + historial FHIR → briefing para el médico.
  Secciones: motivo de consulta, antecedentes relevantes, medicación actual, alertas, preguntas sugeridas.

## dashboard

- [ ] **Interfaz médico**
  Página simple (FastAPI + HTML) donde el médico ve los briefings antes de la consulta.
  Mostrar: nombre paciente, motivo, resumen síntomas, alertas del historial.

## infraestructura

- [ ] **Dockerfiles** para cada servicio (voice-agent, fhir-service, llm-service, dashboard).

- [ ] **Variables de entorno de producción**
  Separar `.env.dev` (Ollama + gTTS) de `.env.prod` (OpenAI + Twilio real).