#!/usr/bin/env bash
# Start the local model server for Mind Map.
# First run downloads Qwen3-4B-Instruct-2507 Q4_K_M (~2.5 GB) into the llama.cpp cache.
set -euo pipefail

MODEL="${MINDMAP_MODEL:-unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M}"
PORT="${MINDMAP_PORT:-8080}"
CTX="${MINDMAP_CTX:-8192}"
THREADS="${MINDMAP_THREADS:-6}"   # i7-9750H has 6 physical cores

if ! command -v llama-server >/dev/null 2>&1; then
  echo "llama-server not found. Install it with: brew install llama.cpp" >&2
  exit 1
fi

exec llama-server \
  -hf "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --threads "$THREADS" \
  --jinja \
  "$@"
