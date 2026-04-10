# HCIS Master Playbook (Fase 2)

Este documento define la fase 2 de la pipeline:
1. Reglas de extracción por tipo documental/recurso.
2. Resolución de conflictos clínicos entre secciones.
3. Checklist de calidad para datos sintéticos de demo.

Implementación de referencia: `fhir-service/hcis_master.py`.

## 1) Reglas de extracción

Bloques documentales objetivo (HCDSNS + RD 1093/2010):
- `ICA` Informe clínico de alta
- `ICCE` Consulta externa
- `ICU` Urgencias
- `ICAP` Atención primaria
- `ICE` Cuidados de enfermería
- `IRPL` Resultados laboratorio
- `IRPI` Resultados imagen
- `IROPD` Otras pruebas diagnósticas
- `HCR` Historia clínica resumida

Mapeo operativo FHIR -> PMR:
- `Patient` -> `patient_demographics`
- `Encounter` -> `encounters` + fragmento para `all_sections`
- `Condition` -> `diagnoses` / `active_problems`
- `Procedure` -> `procedures` (incluye `is_surgery`)
- `MedicationRequest` -> `medications`
- `AllergyIntolerance` -> `allergies_adrs`
- `DiagnosticReport` -> `lab_results` o `imaging_reports` u `other_diagnostic_tests`
- `Observation` -> `lab_results`
- `Composition` -> `discharge_summaries` + `clinical_notes`
- `DocumentReference` -> `document_index` + `attachments` + `clinical_notes`
- `CarePlan` -> `nursing_care`

Reglas de trazabilidad mínimas:
- Todo dato clínico extraído debe tener `source_refs[]`.
- Todo dato relevante para resumen/flags debe tener `evidence_spans[]`.
- `all_sections[]` mantiene fragmentos aptos para embeddings y búsqueda híbrida.

## 2) Resolución de conflictos

### 2.1 Diagnósticos duplicados
- Clave: `code` (o `display` si no hay código).
- Política:
  - Prioridad por estado clínico (`active` > `recurrence` > `remission` > `resolved` > `unknown`).
  - En empate, se conserva el más reciente (`onset_date`).
- Registro de conflicto: `conflict_resolution.conflicts[]`.

### 2.2 Medicación contradictoria
- Clave: código o nombre de fármaco normalizado.
- Política:
  - Prioridad de estado (`active` > `on-hold` > `completed` > `stopped` > `unknown`).
  - En empate, el más reciente (`start_date`).
- Si hay estados distintos para mismo fármaco, marcar `manual_review=true`.

### 2.3 Alergias discordantes
- Clave: agente (`code`/`display`) normalizado.
- Política:
  - Mantener la mayor criticidad (`high` > `low` > `unable-to-assess` > `unknown`).
  - En empate, la más reciente (`recorded_date`).
- Si cambia `verification_status`, marcar `manual_review=true`.

## 3) Checklist de calidad (demo)

Aplicado por `validate_master_record_for_demo`:
- Demográficos mínimos (`patient_id`, `birth_date`, `sex_at_birth`).
- Trazabilidad mínima (`source_refs` + `evidence_spans`).
- Cobertura documental HCDSNS/RD1093 (objetivo >=6/9 en demo).
- Mínimo clínico operativo (>=1 encounter y >=1 nota/alta).
- Índice de búsqueda (`all_sections`) con volumen útil (>=8 fragmentos).

Salida:
- `passes` (bool)
- `score` (0-100)
- `checks[]` con `pass/warn/fail`
- resumen de tipos documentales presentes vs requeridos

## 4) Dataset fake realista

`fhir-service/generate_patients.py` ahora genera pacientes con:
- longitudinalidad (encounters de urgencias + AP + consulta externa)
- condiciones, medicación y alergias
- procedimientos/cirugías
- laboratorio, imagen y otras pruebas
- composiciones (resumen + alta)
- `DocumentReference` con adjuntos `text/plain` y `application/pdf`

Esto permite probar el circuito completo:
- Ingesta FHIR -> PMR -> all_sections -> búsqueda -> evidencia -> resumen/flags.

## 5) Integración de búsqueda (sin implementar scoring aquí)

El servicio expone:
- `GET /fhir/pacientes/{cip}/search`

Comportamiento:
- construye `master_record` del paciente,
- delega la búsqueda en el servicio externo configurado en `SEARCH_SERVICE_URL`,
- retorna la respuesta del buscador para que el dashboard la renderice.

Nota:
- este repo no implementa el motor de ranking/embeddings; solo el contrato de integración.
