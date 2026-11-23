# Mind Map — local LLM chat as a 2D mind map

macOS desktop prototype (Python + PySide6). Every chat session is a node on a
pannable/zoomable 2D map. Sessions branch off each other with an editable
**handoff brief** that carries the relevant context from parent to child.
The model runs locally: Qwen3-4B-Instruct-2507 (Q4_K_M GGUF) via llama.cpp's
`llama-server` (OpenAI-compatible API on localhost).

## Design decisions (agreed with user — don't re-litigate)
- **The mind map is the whole UI. No sidebars.**
- Clicking a node **zooms into it**: chat fills the window, breadcrumb at top
  (`root > idea A > ...`, clickable). **Esc** zooms back out to the map.
- **`/branch <topic>`** (and a Branch button): Qwen writes a handoff brief from
  the current chat → user sees/edits it in a dialog → confirm creates a child
  node → camera **pivots** to the new node and opens it.
- Child context = the brief only (not the parent's full history). Keeps
  branches focused and context small for a 4B CPU model.
- **`/parent`** goes to the parent session.
- Branches can be placed in any direction (N/S/E/W) around the parent.
- **Drag** moves a node with its whole subtree; **⌥-drag** moves only that node.
  Positions persist.
- **⌘+arrow** in chat view: pivot to the nearest connected session in that
  direction.
- Double-click empty canvas: new independent root session.
- **No merging** child conclusions back into the parent.
- Persistence: SQLite (`~/Library/Application Support/MindMap/mindmap.db`).

## Hardware constraints
Intel i7-9750H, 32 GB RAM, no Apple Silicon → no MLX, CPU inference.
Keep context small (server ctx 8192).

## Layout
- `mindmap/store.py` — SQLite sessions/messages, subtree moves
- `mindmap/llm.py` — streaming client for the OpenAI-compatible server
- `mindmap/branching.py` — handoff brief prompt, child context, history trimming
- `mindmap/layout.py` — child placement (N/E/S/W) and directional navigation
- `mindmap/commands.py` — slash-command parsing
- `mindmap/ui/` — PySide6: map view, chat view, brief dialog, main window
- `tests/` — pytest (+ pytest-qt, offscreen) for all of the above
- `scripts/serve.sh` — start llama-server with the Qwen model

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Model server: `scripts/serve.sh` (first run downloads ~2.5 GB)
- App: `.venv/bin/python -m mindmap`
- Tests: `.venv/bin/pytest`

## Conventions
- Atomic git commits, one logical change each.
- Every logic module has tests; UI gets offscreen smoke tests.
- Keep this file updated with state and decisions.

## Status
- [x] Design agreed
- [ ] Core modules + tests
- [ ] UI
- [ ] llama.cpp installed + model downloaded + end-to-end run
