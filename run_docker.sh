#!/bin/sh
# Corre run.py dentro de la imagen de Lean contra Ollama del host (modelos locales, costo 0).
#   sh run_docker.sh --config baseline_a --limit 5
# Goedel servido con Ollama: ver lean/goedel-prover.Modelfile.
export MSYS_NO_PATHCONV=1
exec docker run --rm -v "$(pwd -W 2>/dev/null || pwd):/work" -w /work \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e PROVER_URL=http://host.docker.internal:11434 \
  -e PROVER_MODEL="${PROVER_MODEL:-goedel-prover}" \
  -e PROVER_MAX_TOKENS="${PROVER_MAX_TOKENS:-6144}" \
  -e RETRIEVER_URL="${RETRIEVER_URL:-http://host.docker.internal:8765}" \
  -e PYTHONUNBUFFERED=1 \
  mathagents-lean:v4.15.0 python3 run.py "$@"
