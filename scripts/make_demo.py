"""Record the README demo: the real app, offscreen, with scripted replies.

Usage: python scripts/make_demo.py docs/   (needs ffmpeg on PATH)
Writes docs/demo.gif, docs/map.png, docs/chat.png and docs/picker.png.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from mindmap.mock_llm import tokenize  # noqa: E402
from mindmap.store import Store  # noqa: E402
from mindmap.ui.brief_dialog import BriefDialog  # noqa: E402
from mindmap.ui.main_window import MainWindow  # noqa: E402

FPS = 12
SIZE = (1000, 640)

REPLIES = [
    # Root chat
    "Two days is enough for the highlights. A simple plan:\n\n"
    "- **Day 1:** Alfama and the castle in the morning, Baixa and the river after lunch.\n"
    "- **Day 2:** Belém for the tower and pastéis de nata, then LX Factory.\n\n"
    "Food and day trips could each be their own branch.",
    # Handoff brief
    "## Goal\nFind the best food to try in Lisbon over the weekend.\n\n"
    "## Context\n- Two-day trip: Alfama, Baixa, Belém, LX Factory.\n"
    "- Pastéis de nata in Belém is already on the list.\n\n"
    "## Open questions\n- Which dishes are essential?\n- Where to eat near Alfama?",
    # Child chat
    "Given you're in Alfama and Belém:\n\n"
    "1. **Bifana** — pork sandwich, quick lunch.\n"
    "2. **Grilled sardines** — best at a tasca in Alfama.\n"
    "3. **Bacalhau à Brás** — the classic salt-cod dish.\n"
    "4. **Ginjinha** — cherry liqueur, a shot near Rossio.",
]


class DemoClient:
    """Streams the scripted replies in order, a bit faster than the real model."""

    def __init__(self):
        self.i = 0

    def stream_chat(self, messages, temperature=0.7):
        text = REPLIES[min(self.i, len(REPLIES) - 1)]
        self.i += 1
        time.sleep(0.5)
        for tok in tokenize(text):
            time.sleep(0.045)
            yield tok


class Recorder:
    def __init__(self, app, window, out_dir: Path):
        self.app, self.w, self.dir = app, window, out_dir
        self.n = 0
        self.overlay: QDialog | None = None

    def frame(self, repeat: int = 1) -> None:
        self.app.processEvents()
        img = self.w.grab().toImage()
        if self.overlay is not None:
            p = QPainter(img)
            p.fillRect(img.rect(), QColor(0, 0, 0, 90))
            d = self.overlay.grab().toImage()
            x, y = (img.width() - d.width()) // 2, (img.height() - d.height()) // 2
            p.drawImage(x, y, d)
            p.setPen(QColor(0, 0, 0, 40))
            p.drawRect(QRect(x, y, d.width() - 1, d.height() - 1))
            p.end()
        for _ in range(repeat):
            img.save(str(self.dir / f"f{self.n:05d}.png"))
            self.n += 1

    def hold(self, seconds: float) -> None:
        self.frame(max(1, int(seconds * FPS)))

    def run_for(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            t = time.time()
            self.app.processEvents(QEventLoop.AllEvents, 10)
            self.frame()
            time.sleep(max(0, 1 / FPS - (time.time() - t)))

    def until(self, cond, limit: float = 30) -> None:
        end = time.time() + limit
        while not cond() and time.time() < end:
            self.run_for(1 / FPS)

    def type(self, text: str, per_frame: int = 2) -> None:
        box = self.w.chat.input
        for i in range(0, len(text), per_frame):
            box.setPlainText(text[: i + per_frame])
            box.moveCursor(box.textCursor().MoveOperation.End)
            self.frame()
        self.hold(0.4)


def make_dialog_factory(rec: Recorder):
    class DemoBriefDialog(BriefDialog):
        def exec(self):
            self.resize(520, 380)
            rec.overlay = self
            self.done_flag = False
            self.ok.setEnabled(False)
            rec.until(lambda: self.ok.isEnabled(), limit=40)
            rec.hold(1.2)
            rec.overlay = None
            return QDialog.Accepted

    return DemoBriefDialog


def main(out: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    store = Store()
    w = MainWindow(store, DemoClient())
    w.resize(*SIZE)
    w.show()
    w.map.animation_ms = 700
    w.set_model_status("ready", "Qwen3 4B ready")

    frames = Path(tempfile.mkdtemp(prefix="mindmap-demo-"))
    rec = Recorder(app, w, frames)
    w.brief_dialog_factory = make_dialog_factory(rec)

    root = store.sessions()[0]
    store.rename(root.id, "Weekend in Lisbon")
    w.map.set_title(root.id, "Weekend in Lisbon")
    w.map.center_on_node(root.id, 1.0)
    rec.hold(1.2)

    # 1. Zoom into the root and chat.
    w.open_session(root.id)
    rec.until(w.in_chat)
    rec.hold(0.3)
    rec.type("Plan a 2-day weekend in Lisbon for me.")
    w.handle_input(w.chat.input.toPlainText())
    rec.until(w.idle)
    rec.hold(1.5)

    # 2. Branch: the brief streams in, then the camera pivots to the child.
    rec.type("/branch food to try")
    w.handle_input(w.chat.input.toPlainText())
    rec.until(w.in_chat, limit=10)
    rec.hold(1.5)

    # 3. The child sees only the brief, and answers from it.
    rec.type("What should I eat?")
    w.handle_input(w.chat.input.toPlainText())
    rec.until(w.idle)
    rec.hold(1.8)

    # 4. Back out to the map; more branches grow around the root.
    w.back_to_map()
    rec.run_for(0.9)
    for title in ["Day trip to Sintra", "Where to stay"]:
        w.current_id = root.id
        w.create_branch(root.id, title, "## Goal\n" + title)
        w.stack.setCurrentWidget(w.map)
        w.map.animate_camera(w.map.nodes[root.id].pos(), 0.85)
        rec.run_for(0.8)
    child = next(s for s in store.sessions() if s.title == "food to try")
    w.create_branch(child.id, "Pastéis de nata spots", "## Goal\nBest nata.")
    w.stack.setCurrentWidget(w.map)
    pts = [n.pos() for n in w.map.nodes.values()]
    centre = sum(pts[1:], pts[0]) / len(pts)
    w.map.animate_camera(centre, 0.8)
    rec.run_for(1.0)
    rec.hold(2.5)

    # Encode with a generated palette for a small, clean GIF.
    gif = out_dir / "demo.gif"
    palette = frames / "palette.png"
    common = ["-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%05d.png")]
    scale = "scale=860:-1:flags=lanczos"
    subprocess.run(["ffmpeg", *common, "-vf", f"{scale},palettegen=stats_mode=diff", str(palette)], check=True)
    subprocess.run(
        ["ffmpeg", *common, "-i", str(palette), "-lavfi",
         f"{scale}[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle", str(gif)],
        check=True,
    )

    # Stills: the map and a chat.
    w.grab().save(str(out_dir / "map.png"))
    w.open_session(child.id)
    rec.until(w.in_chat)
    w.chat.brief_card.toggle.setChecked(True)
    app.processEvents()
    w.grab().save(str(out_dir / "chat.png"))

    # The model picker, on the Claude tab.
    from mindmap.models import ModelSpec
    from mindmap.ui import style
    from mindmap.ui.model_picker import ModelPickerDialog

    picker = ModelPickerDialog(
        ModelSpec("anthropic", "claude-opus-5-5"),
        get_key=lambda p: None, key_source=lambda p: None,
        set_key=lambda *a: None, delete_key=lambda *a: None, list_models=lambda *a: [],
    )
    picker.setStyleSheet(style.stylesheet(style.LIGHT))
    picker.resize(560, 380)
    picker.show()
    app.processEvents()
    picker.grab().save(str(out_dir / "picker.png"))

    shutil.rmtree(frames)
    print(f"{gif} ({gif.stat().st_size // 1024} KB, {rec.n} frames)")
    w.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs")
