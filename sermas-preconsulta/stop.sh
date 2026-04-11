#!/bin/bash
# Para todos los servicios de SERMAS Pre-Consulta
echo "Parando servicios..."
pkill -f "uvicorn.*--app-dir .*sermas-preconsulta/fhir-service.*--port 8001" 2>/dev/null && echo "  → fhir-service parado" || true
pkill -f "uvicorn.*--app-dir .*sermas-preconsulta/llm-service.*--port 8002" 2>/dev/null && echo "  → llm-service parado" || true
if command -v fuser >/dev/null 2>&1; then
	fuser -k 8001/tcp >/dev/null 2>&1 || true
	fuser -k 8002/tcp >/dev/null 2>&1 || true
fi
echo "Hecho. Ollama sigue corriendo (páralo tú si quieres con: pkill ollama)"