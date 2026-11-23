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
- **Model per topic:** a new root opens the model picker (cancel = no root);
  branches inherit the parent's model; any chat can switch via the header chip
  or node menu. Providers: local llama.cpp (presets or any HF GGUF), Claude
  (Anthropic SDK, server-side refusal fallback on supported models, no
  temperature), ChatGPT (OpenAI SDK). Keys in macOS Keychain (`keys.py`), env
  vars win. One local model at a time: switching restarts our llama-server.
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
- `mindmap/server.py` — starts/watches/stops llama-server from inside the app
- `scripts/serve.sh` — start llama-server by hand (dev)
- `scripts/build_app.sh` — build `dist/Mind Map.app` (PyInstaller + bundled llama-server)

## Commands
- Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Model server: `scripts/serve.sh` (first run downloads ~2.5 GB to `~/.cache/huggingface/hub`)
- App: `.venv/bin/python -m mindmap`
- **App without a model:** `.venv/bin/python -m mindmap --mock --demo`
  (`--reset-demo` re-seeds; demo uses `demo.db`, never the real `mindmap.db`)
- Tests: `.venv/bin/pytest`
- **Build the Mac app:** `scripts/build_app.sh` → `dist/Mind Map.app` (~160 MB;
  model not bundled, uses `~/.cache/huggingface`). Logs: `~/Library/Logs/MindMap/`

## Mock + demo
- `mindmap/mock_llm.py` — `MockLLMClient`, same interface as `LLMClient`.
  Keyword-scripted replies; branch requests get a brief built from the real
  parent messages (and the parent's goal), so context transfer is visible.
- `mindmap/demo.py` — 13-node demo map (coffee roastery + Kyoto trip), up to
  4 levels deep, hand-written conversations and briefs; positions come from
  the real `place_child`.
- `tests/test_stress.py` — drives the real MainWindow with the mock: deep
  branch chains, 12-way fan-out, full-tree navigation, concurrent replies,
  drag + reload from disk, and seeded random walks (150 actions) checking
  map/store/chat invariants after every step.
- Threads: workers must stay referenced until `finished` + `wait()`
  (`MainWindow._track`) — dropping them early aborts the process.

## Conventions
- Atomic git commits, one logical change each.
- **Never** add "Co-Authored-By: Claude" or any Claude/AI attribution to
  commits, PRs, or files.
- Every logic module has tests; UI gets offscreen smoke tests.
- Keep this file updated with state and decisions.

## Implementation notes
- ⌘+arrow navigation only fires when the chat input is **empty**, so ⌘← / ⌘→
  still work for text editing while typing.
- `//text` sends a literal message starting with `/`.
- A new root titled "New chat" is renamed from its first user message.
- Map: trackpad scroll pans; pinch or ⌘-scroll zooms; mouse wheel zooms.
- Connected nodes for ⌘+arrow = parent + children (not siblings/cousins).
- Env overrides: `MINDMAP_DB`, `MINDMAP_LLM_URL`; serve.sh: `MINDMAP_MODEL`,
  `MINDMAP_PORT`, `MINDMAP_CTX`, `MINDMAP_THREADS`.
- Tests use `FakeClient` / `FakeBriefDialog` and `animation_ms = 0`.

## Status (2026-11-22)
- [x] Design agreed
- [x] Core modules + tests (store, llm, branching, layout, commands)
- [x] UI (map view, chat view, brief dialog, main window) + tests
- [x] Mock Qwen, demo map, stress tests — 91 passing
- [x] Offscreen launch smoke test passes
- [x] llama.cpp b12648 prebuilt (macOS x64, CPU) in `~/.local/llama.cpp/current`
  — Homebrew abandoned: no Intel bottles on macOS 26, built everything from source
- [x] Model downloaded; real Qwen streams ~8–9 words/s, first token ~0.3 s
- [x] Real end-to-end branching works (parent chat → /branch → child chat).
  Brief ~16–25 s, normal replies 8–20 s; long unprompted replies can take 90 s.
- Brief prompt sends the parent chat as a quoted TRANSCRIPT in one message —
  as chat turns, Qwen3-4B reversed stated conclusions (see commit 3fda70d).
- [x] Replies capped at 512 tokens (`DEFAULT_MAX_TOKENS`) with a visible cut-off
  note; system prompt asks for brief, emoji-free answers. Same prompt: 92 s → 17 s.
- [x] Chat restyle: bubbles, foldable brief card, code blocks with Copy,
  thinking indicator, growing input, shared light/dark palette (`ui/style.py`)
- [x] Rename/delete from right-click on a node or the chat ⋯ menu; delete
  takes the whole subtree after confirming
- [x] App starts its own llama-server if none is running, stops it on quit;
  status label shows Starting/Loading/Ready/Stopped
- [x] Packaged as `dist/Mind Map.app` (ad-hoc signed, works when opened from Finder)
- [x] Model choice per topic: local / Claude / ChatGPT (`models.py`,
  `providers.py`, `ui/model_picker.py`). Claude/OpenAI tested with fake SDK
  clients only — no API keys on this machine yet.
- Next ideas: reparent instead of deleting children; undo delete; notarized build
