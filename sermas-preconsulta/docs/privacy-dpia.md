# DPIA — Evaluación de Impacto en Protección de Datos
## SERMAS Pre-Consulta · Agente de Voz para Gestión de Citas

**Versión:** 0.1 (prototipo hackathon)
**Fecha:** 2026-04-10
**Autora:** María Romero Huertas
**Estado:** Borrador — pendiente de revisión por DPO antes de producción

---

## 1. ¿Por qué es obligatorio hacer esta DPIA?

El artículo 35 del RGPD obliga a realizar una DPIA cuando el tratamiento de datos supone un **alto riesgo** para los derechos de las personas. Este proyecto cumple dos de los criterios que lo activan automáticamente:

- **Datos de categoría especial (Art. 9 RGPD):** datos de salud — síntomas, historial clínico, medicación.
- **Tratamiento a escala:** el 900 102 112 gestiona miles de llamadas diarias.

Además, el tratamiento implica perfilado automático (el LLM genera un briefing clínico) y decisiones que afectan al acceso a servicios sanitarios.

---

## 2. Descripción del tratamiento

| Campo | Descripción |
|---|---|
| **Nombre del sistema** | SERMAS Pre-Consulta |
| **Finalidad** | Recoger síntomas del paciente durante la gestión telefónica de una cita médica y generar un briefing pre-consulta para el profesional sanitario |
| **Base jurídica** | Art. 9.2.h RGPD — tratamiento necesario para la prestación de asistencia sanitaria; Art. 6.1.e — interés público en el ámbito de la salud pública |
| **Responsable del tratamiento** | SERMAS — Servicio Madrileño de Salud |
| **Encargado del tratamiento** | Proveedor tecnológico (a definir en contrato DPA) |
| **Categorías de interesados** | Pacientes del SERMAS que gestionan citas por teléfono |
| **Categorías de datos** | CIP, síntomas referidos, historial clínico (diagnósticos, medicación, alergias, visitas anteriores), voz |
| **Destinatarios** | Médico asignado a la consulta (solo el briefing final, no la transcripción) |
| **Transferencias internacionales** | Ver sección 5 |
| **Plazo de conservación** | A definir por SERMAS; mínimo hasta la realización de la consulta |

---

## 3. Flujo de datos y dónde vive cada dato

```
Paciente (voz)
    │
    ▼
[Twilio]  ── audio en streaming ──►  [voice-agent]
                                          │
                              STT (Whisper local o API)
                                          │
                              LLM extrae síntomas + CIP
                                          │
                                          ▼
                                   [fhir-service]
                                          │
                              Busca historial por CIP
                              en servidor FHIR SERMAS
                                          │
                                          ▼
                                   [llm-service]
                                          │
                              GPT-4o genera briefing
                                          │
                                          ▼
                              DocumentReference FHIR
                              guardado en Historia Clínica
                                          │
                                          ▼
                                    [dashboard]
                                    Médico lo ve
```

---

## 4. Análisis de riesgos

### 4.1 Riesgos identificados

| ID | Riesgo | Probabilidad | Impacto | Nivel |
|---|---|---|---|---|
| R1 | Intercepción del audio en tránsito (llamada Twilio) | Media | Alto | **Alto** |
| R2 | Filtración de datos clínicos por log accidental | Alta | Alto | **Alto** |
| R3 | El LLM extrae datos incorrectos (alucinación) y afecta a la consulta | Media | Alto | **Alto** |
| R4 | Acceso no autorizado al dashboard por el médico equivocado | Media | Alto | **Alto** |
| R5 | Audio del paciente procesado por terceros (gTTS, OpenAI Whisper API) | Alta | Medio | **Medio** |
| R6 | Retención de audio más allá de lo necesario | Baja | Alto | **Medio** |
| R7 | Uso del sistema fuera del contexto sanitario | Baja | Alto | **Medio** |

### 4.2 Análisis detallado de los riesgos más críticos

**R1 — Intercepción de audio**
Twilio transmite el audio del paciente por WebSocket. Si no se usa WSS (TLS), el audio viaja en claro por la red.
→ Mitigación: usar exclusivamente WSS en producción. Nunca WS en claro. Verificar certificados TLS.

**R3 — Alucinaciones del LLM**
El LLM puede malinterpretar síntomas o inventar información clínica. Si el médico actúa sobre un briefing incorrecto, hay riesgo clínico.
→ Mitigación: el briefing debe mostrarse siempre como **ayuda a la decisión, no como diagnóstico**. El médico siempre realiza su propia anamnesis. Añadir disclaimer visible en el dashboard.

**R5 — Datos procesados por terceros**
- **gTTS (prototipo):** el texto de las respuestas del agente se envía a Google para sintetizar voz. En el prototipo esto no incluye datos del paciente (son respuestas genéricas del agente), pero hay que verificarlo en cada turno.
- **OpenAI Whisper API (producción):** el audio del paciente se envía a OpenAI. Requiere DPA firmado con OpenAI y evaluación de transferencia internacional (EE.UU.).
- **OpenAI GPT-4o (producción):** síntomas y fragmentos del historial se envían a OpenAI. Mismo requisito.

→ Mitigación en producción: usar modelos on-premise (Whisper local + LLM en infraestructura del SERMAS) o garantizar DPA adecuado. Ollama + faster-whisper eliminan este riesgo.

---

## 5. Transferencias internacionales

| Servicio | País | Base de transferencia | Estado en prototipo |
|---|---|---|---|
| Twilio (voz) | EE.UU. | Cláusulas Contractuales Tipo (SCCs) | Necesario para llamadas |
| OpenAI Whisper API | EE.UU. | SCCs + DPA | Solo si se activa en producción |
| OpenAI GPT-4o | EE.UU. | SCCs + DPA | Solo si se activa en producción |
| gTTS (Google TTS) | EE.UU. | SCCs | Activo en prototipo — solo texto del agente, no del paciente |
| Ollama (LLM local) | — | No hay transferencia | Activo en prototipo |
| faster-whisper (STT local) | — | No hay transferencia | Activo en prototipo |

**El prototipo está diseñado para minimizar transferencias internacionales** usando Ollama y faster-whisper en local. El único servicio externo activo que toca datos es Twilio (necesario para la telefonía) y gTTS (solo texto de respuestas del agente, no datos del paciente).

---

## 6. Medidas técnicas y organizativas

### Implementadas en el prototipo
- [x] Datos sintéticos exclusivamente (Synthea) — ningún dato real de pacientes reales
- [x] STT local (faster-whisper) — el audio no sale del servidor
- [x] LLM local (Ollama) — los síntomas no salen del servidor
- [x] No se loggean datos personales en los módulos actuales

### Necesarias antes de producción
- [ ] TLS/WSS obligatorio en todos los endpoints
- [ ] Autenticación del médico en el dashboard (OAuth2 con el SSO del SERMAS)
- [ ] Cifrado en reposo de DocumentReference y transcripciones
- [ ] Política de retención y borrado automático de audio (máximo 24h)
- [ ] Auditoría de accesos (quién vio qué briefing y cuándo)
- [ ] DPA firmado con Twilio como encargado del tratamiento
- [ ] DPA firmado con OpenAI si se activan sus APIs en producción
- [ ] Información al paciente al inicio de la llamada (Art. 13 RGPD):
  *"Esta llamada puede ser procesada por un sistema automático para preparar su consulta. Sus datos se tratarán conforme a la política de privacidad del SERMAS disponible en..."*
- [ ] Mecanismo de opt-out: el paciente puede pedir hablar con un agente humano
- [ ] Revisión por el DPO del SERMAS
- [ ] Registro de actividades de tratamiento (Art. 30 RGPD)

---

## 7. Conclusión

**El prototipo es seguro para su uso en un hackathon** porque:
1. Usa únicamente datos sintéticos — no hay pacientes reales.
2. El procesamiento de voz y LLM es local — los datos no salen del ordenador.
3. El único dato que sale es el texto de las respuestas del agente (no del paciente) vía gTTS.

**No es apto para producción** sin completar las medidas de la sección 6 y obtener la aprobación del DPO del SERMAS.

---

## 8. Próximos pasos para producción

1. Presentar esta DPIA al DPO del SERMAS para revisión.
2. Firmar DPA con Twilio (ya disponen de plantilla estándar para sanidad).
3. Decidir arquitectura de LLM: on-premise (sin transferencias) vs. cloud con DPA.
4. Implementar el aviso al paciente al inicio de la llamada.
5. Definir política de retención de datos con el área jurídica del SERMAS.