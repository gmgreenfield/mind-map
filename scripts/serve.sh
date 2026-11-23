#!/usr/bin/env bash
# Start the local model server for Mind Map.
# First run downloads Qwen3-4B-Instruct-2507 Q4_K_M (~2.5 GB) into the llama.cpp cache.
set -euo pipefail

MODEL="${MINDMAP_MODEL:-unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M}"
PORT="${MINDMAP_PORT:-8080}"
CTX="${MINDMAP_CTX:-8192}"
THREADS="${MINDMAP_THREADS:-6}"   # i7-9750H has 6 physical cores

# Prefer $LLAMA_SERVER, then the prebuilt release in ~/.local/llama.cpp/current,
# then whatever is on PATH.
LOCAL_BUILD="$HOME/.local/llama.cpp/current/llama-server"
if [[ -n "${LLAMA_SERVER:-}" ]]; then
  SERVER="$LLAMA_SERVER"
elif [[ -x "$LOCAL_BUILD" ]]; then
  SERVER="$LOCAL_BUILD"
elif command -v llama-server >/dev/null 2>&1; then
  SERVER="$(command -v llama-server)"
else
  cat >&2 <<EOF
llama-server not found. Download the macOS build from
https://github.com/ggml-org/llama.cpp/releases (llama-<build>-bin-macos-x64.tar.gz),
extract it under ~/.local/llama.cpp/<build>, and link it:
  ln -sfn ~/.local/llama.cpp/<build>/llama-<build> ~/.local/llama.cpp/current
EOF
  exit 1
fi

exec "$SERVER" \
  -hf "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --threads "$THREADS" \
  --jinja \
  "$@"
