# HCIS Master Record (prototipo)

Este directorio contiene un primer dataset sintetico para simular una historia clinica hospitalaria estilo HCIS:

- `schema/patient_master_record.schema.json`: esquema maestro del JSON unificado.
- `profiles/2800001234_master_record.json`: perfil fake completo con trazabilidad.
- `documents/2800001234/*`: adjuntos de ejemplo (PDF y TXT).

## Objetivo

Usar un unico JSON grande por paciente como fuente de verdad para:

1. generar embeddings por fragmento;
2. ejecutar busqueda hibrida;
3. construir la vista limpia del dashboard;
4. justificar cada dato con evidencia trazable.

## Siguiente paso tecnico

Implementar un ingestor que lea:

- FHIR Bundle (`Patient`, `Encounter`, `Condition`, etc.),
- `DocumentReference` con adjuntos PDF/TXT,
- notas libres y documentos de alta/urgencias/consulta externa.

Y escriba automaticamente el `patient_master_record.json` validado contra el schema.
