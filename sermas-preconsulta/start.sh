#!/bin/bash
# Lanza todos los servicios de SERMAS Pre-Consulta en background
# Uso: ./start.sh
# Para parar todo: ./stop.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Iniciando SERMAS Pre-Consulta..."

# Ollama
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "  → Arrancando Ollama..."
  ollama serve > /tmp/sermas-ollama.log 2>&1 &
  sleep 3
else
  echo "  → Ollama ya está corriendo"
fi

VENV="$ROOT/../.venv"

# LLM service
echo "  → Arrancando llm-service (puerto 8002)..."
LLM_BACKEND=ollama OLLAMA_MODEL=llama3.1:8b \
  "$VENV/bin/uvicorn" main:app \
  --app-dir "$ROOT/llm-service" \
  --port 8002 --log-level warning > /tmp/sermas-llm.log 2>&1 &

sleep 2

# FHIR service + dashboard
echo "  → Arrancando fhir-service + dashboard (puerto 8001)..."
LLM_SERVICE_URL=http://localhost:8002 \
  "$VENV/bin/uvicorn" main:app \
  --app-dir "$ROOT/fhir-service" \
  --port 8001 --log-level warning > /tmp/sermas-fhir.log 2>&1 &

sleep 2

# Verificar
if curl -s http://localhost:8001/health > /dev/null; then
  echo ""
  echo "  Servicios arriba. Abriendo dashboard..."
  if command -v open > /dev/null; then
    open http://localhost:8001
  elif command -v xdg-open > /dev/null; then
    xdg-open http://localhost:8001
  else
    python3 -m webbrowser http://localhost:8001 &>/dev/null
  fi
else
  echo "  [ERROR] fhir-service no responde. Ver /tmp/sermas-fhir.log"
fi