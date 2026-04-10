#!/bin/bash
# Para todos los servicios de SERMAS Pre-Consulta
echo "Parando servicios..."
pkill -f "uvicorn main:app --port 8001" 2>/dev/null && echo "  → fhir-service parado" || true
pkill -f "uvicorn main:app --port 8002" 2>/dev/null && echo "  → llm-service parado" || true
echo "Hecho. Ollama sigue corriendo (páralo tú si quieres con: pkill ollama)"