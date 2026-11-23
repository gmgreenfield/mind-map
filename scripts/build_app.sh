#!/usr/bin/env bash
# Build "dist/Mind Map.app": the Python app plus a bundled llama-server.
# The Qwen model itself (~2.5 GB) is not bundled; llama-server downloads it
# to ~/.cache/huggingface on first launch and reuses it after that.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
LLAMA_DIR="${LLAMA_DIR:-$HOME/.local/llama.cpp/current}"
BUILD=build
STAGE="$BUILD/llama"

"$PY" -m pip install -q -r requirements.txt -r requirements-build.txt

if [[ ! -x "$LLAMA_DIR/llama-server" ]]; then
  echo "llama-server not found in $LLAMA_DIR (set LLAMA_DIR)" >&2
  exit 1
fi

echo "==> Staging llama-server and the libraries it needs"
rm -rf "$STAGE" && mkdir -p "$STAGE"
"$PY" - "$LLAMA_DIR" "$STAGE" <<'EOF'
import os, re, shutil, subprocess, sys
src, dst = sys.argv[1], sys.argv[2]
todo, seen = ["llama-server"], set()
while todo:
    name = todo.pop()
    if name in seen:
        continue
    seen.add(name)
    shutil.copy2(os.path.realpath(os.path.join(src, name)), os.path.join(dst, name))
    out = subprocess.run(["otool", "-L", os.path.join(src, name)], capture_output=True, text=True).stdout
    todo += re.findall(r"@rpath/(\S+)", out)
print(f"   {len(seen)} files: {', '.join(sorted(seen))}")
EOF

echo "==> Drawing the icon"
rm -rf "$BUILD/MindMap.iconset"
"$PY" scripts/make_icon.py "$BUILD/MindMap.iconset"
iconutil -c icns "$BUILD/MindMap.iconset" -o "$BUILD/MindMap.icns"

echo "==> Building the app"
add_bins=()
for f in "$STAGE"/*; do add_bins+=(--add-binary "$f:llama"); done
"$PY" -m PyInstaller --noconfirm --clean --windowed \
  --name "Mind Map" \
  --icon "$BUILD/MindMap.icns" \
  --osx-bundle-identifier local.mindmap.app \
  --paths . \
  "${add_bins[@]}" \
  --exclude-module tkinter \
  --exclude-module pytest \
  scripts/app_entry.py

echo "==> Done: dist/Mind Map.app ($(du -sh "dist/Mind Map.app" | cut -f1))"
