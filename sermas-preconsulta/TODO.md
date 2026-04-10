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

- [ ] **Implementar fhir_client.py con datos Synthea**
  Cargar pacientes sintéticos generados con Synthea en formato FHIR R4.
  Buscar por CIP y devolver Bundle con Condition, MedicationRequest, AllergyIntolerance.

- [ ] **Endpoint real `/fhir/preconsulta`**
  Sustituir el stub actual por la lógica completa:
  buscar historial → combinar con síntomas → llamar al llm-service → devolver DocumentReference.

- [ ] **Integración con CIP real del SERMAS**
  En producción, el CIP autentica contra el sistema del SERMAS vía FHIR Patient/$match.

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