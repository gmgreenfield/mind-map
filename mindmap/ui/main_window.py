"""Wires the map, chat view, store and model together."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
)

from .. import branching
from ..commands import Command, CommandError, parse, unescape
from ..layout import Point, nearest_in_direction, place_child
from ..models import COMPANIES, DEFAULT_MODEL, ModelSpec
from ..store import Session, Store
from .brief_dialog import BriefDialog
from .chat_view import ChatView
from . import style
from .map_view import MapView
from .model_picker import pick_model
from .worker import StreamWorker

NEW_CHAT = "New chat"


class MainWindow(QMainWindow):
    def __init__(self, store: Store, client, server=None, parent=None):
        super().__init__(parent)
        self.server = server
        self.setWindowTitle("Mind Map")
        self.resize(1200, 800)
        self.store = store
        self.client = client
        self.current_id: int | None = None
        self.partials: dict[int, str] = {}  # session id -> text streamed so far
        self.workers: dict[int, StreamWorker] = {}
        self._background: set[StreamWorker] = set()
        self.brief_dialog_factory = BriefDialog
        # Swappable in tests: (title, label, text) -> (text, ok) and (title, text) -> bool
        # (current ModelSpec) -> chosen ModelSpec or None; swappable in tests
        self.pick_model = lambda current: pick_model(current, self)
        self.last_model: ModelSpec = DEFAULT_MODEL
        self._status_html = ""
        self.ask_text = lambda title, label, text: QInputDialog.getText(
            self, title, label, text=text
        )
        self.confirm = lambda title, text: (
            QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.Cancel)
            == QMessageBox.Yes
        )

        self.map = MapView()
        self.chat = ChatView()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.map)
        self.stack.addWidget(self.chat)
        self.setCentralWidget(self.stack)
        self.setStyleSheet(style.stylesheet(style.current()))

        self.map.nodeActivated.connect(self.open_session)
        self.map.nodesMoved.connect(self._persist_positions)
        self.map.createRootRequested.connect(self.create_root)
        self.map.nodeMenuRequested.connect(self._node_menu)
        self.chat.sendRequested.connect(self.handle_input)
        self.chat.backRequested.connect(self.back_to_map)
        self.chat.branchRequested.connect(self._branch_button)
        self.chat.sessionRequested.connect(self.pivot_to)
        self.chat.navigateRequested.connect(self.navigate)
        self.chat.renameRequested.connect(lambda: self.rename_session(self.current_id))
        self.chat.deleteRequested.connect(lambda: self.delete_session(self.current_id))
        self.chat.modelRequested.connect(lambda: self.choose_model(self.current_id))

        if not self.store.sessions():
            self.store.create_session(NEW_CHAT, x=0, y=0)
        sessions = self.store.sessions()
        self.map.load(sessions)
        self.map.center_on_node(sessions[0].id)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_model_status)
        if server is not None:
            self.poll_model_status()
            self._status_timer.start(1000)

    # --- view state ---------------------------------------------------------
    def in_chat(self) -> bool:
        return self.stack.currentWidget() is self.chat

    def open_session(self, session_id: int) -> None:
        self.current_id = session_id
        self.map.set_current(session_id)
        self.map.zoom_into(session_id, on_done=lambda: self._show_chat(session_id))

    def _show_chat(self, session_id: int) -> None:
        if self.current_id != session_id:
            return
        self.refresh_chat()
        self.stack.setCurrentWidget(self.chat)
        self.chat.focus_input()

    def refresh_chat(self) -> None:
        sid = self.current_id
        if sid is None:
            return
        self.chat.show_session(
            self.store.ancestry(sid), self.store.messages(sid), self.partials.get(sid)
        )
        spec = self.spec_for(sid)
        self.chat.set_model_label(spec.label, cloud=not spec.is_local)
        self._update_chat_status()

    def back_to_map(self) -> None:
        self.stack.setCurrentWidget(self.map)
        if self.current_id is not None:
            self.map.zoom_out_from(self.current_id)
        self.map.setFocus()

    def pivot_to(self, session_id: int) -> None:
        from_id = self.current_id
        if from_id == session_id and self.in_chat():
            return
        self.current_id = session_id
        self.map.set_current(session_id)
        self.stack.setCurrentWidget(self.map)
        self.map.pivot(from_id, session_id, on_done=lambda: self._show_chat(session_id))

    def navigate(self, direction: str) -> None:
        if self.current_id is None:
            return
        cur = self.store.get_session(self.current_id)
        connected = self.store.children(cur.id)
        if cur.parent_id is not None:
            connected.append(self.store.get_session(cur.parent_id))
        target = nearest_in_direction(
            (cur.x, cur.y), [Point(s.id, s.x, s.y) for s in connected], direction
        )
        if target is None:
            self.chat.flash(f"No connected session to the {_DIR_NAMES[direction]}.")
            return
        self.pivot_to(target.id)

    # --- sessions -------------------------------------------------------------
    def create_root(self, x: float, y: float) -> Session | None:
        """A new topic starts by choosing its model; cancelling creates nothing."""
        spec = self.pick_model(self.last_model)
        if spec is None:
            return None
        self.last_model = spec
        s = self.store.create_session(NEW_CHAT, x=x, y=y, model=str(spec))
        self.map.add_node(s)
        self.open_session(s.id)
        return s

    # --- models ------------------------------------------------------------------
    def spec_for(self, sid: int) -> ModelSpec:
        return ModelSpec.parse(self.store.get_session(sid).model)

    def client_for(self, sid: int):
        """The client for a session's model (a plain test/mock client serves all)."""
        router = getattr(self.client, "client_for", None)
        return router(self.spec_for(sid)) if router else self.client

    def choose_model(self, sid: int | None) -> bool:
        if sid is None:
            return False
        spec = self.pick_model(self.spec_for(sid))
        if spec is None:
            return False
        self.last_model = spec
        self.store.set_model(sid, str(spec))
        self.map.set_model_label(sid, spec.label)
        if sid == self.current_id and self.in_chat():
            self.refresh_chat()
        return True

    def create_branch(self, parent_id: int, title: str, brief: str) -> Session:
        parent = self.store.get_session(parent_id)
        grandparent = (
            self.store.get_session(parent.parent_id) if parent.parent_id is not None else None
        )
        occupied = [(s.x, s.y) for s in self.store.sessions()]
        x, y = place_child(
            (parent.x, parent.y),
            occupied,
            (grandparent.x, grandparent.y) if grandparent else None,
        )
        child = self.store.create_session(
            branching.title_from_text(title),
            parent_id=parent_id,
            brief=brief,
            x=x,
            y=y,
            model=parent.model,  # branches inherit the parent's model
        )
        self.map.add_node(child)
        self.pivot_to(child.id)
        return child

    def _exists(self, sid: int) -> bool:
        try:
            self.store.get_session(sid)
            return True
        except KeyError:
            return False

    def _node_menu(self, sid: int, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.open_session(sid))
        menu.addAction("Rename…", lambda: self.rename_session(sid))
        menu.addAction("Model…", lambda: self.choose_model(sid))
        menu.addSeparator()
        menu.addAction("Delete…", lambda: self.delete_session(sid))
        menu.exec(pos)

    def rename_session(self, sid: int | None, title: str | None = None) -> bool:
        if sid is None:
            return False
        if title is None:
            title, ok = self.ask_text("Rename", "Title:", self.store.get_session(sid).title)
            if not ok:
                return False
        title = " ".join(title.split())
        if not title:
            return False
        self.store.rename(sid, title)
        self.map.set_title(sid, title)
        if self.in_chat() and self.current_id is not None:
            self.refresh_chat()  # breadcrumb may include it
        return True

    def delete_session(self, sid: int | None) -> bool:
        """Delete a session and every branch below it, after confirming."""
        if sid is None:
            return False
        session = self.store.get_session(sid)
        ids = self.store.subtree_ids(sid)
        below = len(ids) - 1
        detail = f" and the {below} branch{'es' if below != 1 else ''} below it" if below else ""
        if not self.confirm("Delete", f"Delete “{session.title}”{detail}? This can't be undone."):
            return False

        for i in ids:
            worker = self.workers.pop(i, None)
            if worker is not None:
                worker.stop()
            self.partials.pop(i, None)
        self.store.delete_session(sid)
        self.map.remove_nodes(ids)

        if self.current_id in ids:
            self.current_id = session.parent_id
            self.map.set_current(self.current_id)
            if self.current_id is not None and self.in_chat():
                self._show_chat(self.current_id)
            elif self.in_chat():
                self.stack.setCurrentWidget(self.map)
        return True

    def _persist_positions(self, moved: list) -> None:
        for sid, x, y in moved:
            self.store.set_position(sid, x, y)

    # --- input ------------------------------------------------------------------
    def handle_input(self, text: str) -> None:
        cmd = parse(text)
        if isinstance(cmd, CommandError):
            self.chat.flash(cmd.message)
            return
        if isinstance(cmd, Command):
            self.chat.clear_input()
            if cmd.name == "branch":
                self.start_branch(cmd.arg)
            elif cmd.name == "parent":
                parent_id = self.store.get_session(self.current_id).parent_id
                if parent_id is None:
                    self.chat.flash("This session is a root — it has no parent.")
                else:
                    self.pivot_to(parent_id)
            elif cmd.name == "map":
                self.back_to_map()
            return
        self.send_message(unescape(text))

    def _branch_button(self) -> None:
        self.chat.input.setPlainText("/branch ")
        self.chat.input.moveCursor(self.chat.input.textCursor().MoveOperation.End)
        self.chat.focus_input()

    def send_message(self, text: str) -> None:
        sid = self.current_id
        if sid is None:
            return
        if sid in self.workers:
            self.chat.flash("Qwen is still replying in this session.")
            return
        session = self.store.get_session(sid)
        if session.title == NEW_CHAT and not self.store.messages(sid):
            title = branching.title_from_text(text)
            self.store.rename(sid, title)
            self.map.set_title(sid, title)
        self.store.add_message(sid, "user", text.strip())
        self.chat.clear_input()

        context = branching.chat_context(session.brief, self.store.messages(sid))
        worker = StreamWorker(self.client_for(sid), context)
        self.workers[sid] = worker
        self.partials[sid] = ""
        self.map.set_busy(sid, True)
        worker.token.connect(lambda d, sid=sid: self._on_token(sid, d))
        worker.done.connect(lambda full, sid=sid: self._on_reply_done(sid, full))
        worker.failed.connect(lambda err, sid=sid: self._on_reply_failed(sid, err))
        self._track(worker)
        self.refresh_chat()
        worker.start()

    def _on_token(self, sid: int, delta: str) -> None:
        self.partials[sid] = self.partials.get(sid, "") + delta
        if sid == self.current_id and self.in_chat():
            self.chat.set_partial(self.partials[sid])

    def _finish_reply(self, sid: int, text: str) -> None:
        self.workers.pop(sid, None)
        self.partials.pop(sid, None)
        if not self._exists(sid):  # deleted while Qwen was replying
            return
        if text.strip():
            self.store.add_message(sid, "assistant", text.strip())
        self.map.set_busy(sid, False)
        if sid == self.current_id:
            self.refresh_chat()

    def _on_reply_done(self, sid: int, full: str) -> None:
        self._finish_reply(sid, full)

    def _on_reply_failed(self, sid: int, error: str) -> None:
        self._finish_reply(sid, self.partials.get(sid, ""))
        if sid == self.current_id:
            self.chat.flash(error)

    def start_branch(self, topic: str) -> Session | None:
        parent = self.store.get_session(self.current_id)
        dialog = self.brief_dialog_factory(topic, self)
        request = branching.brief_request(parent.brief, self.store.messages(parent.id), topic)
        worker = StreamWorker(self.client_for(parent.id), request, temperature=0.3)
        worker.token.connect(dialog.append)
        worker.done.connect(dialog.finish)
        worker.failed.connect(dialog.fail)
        self._track(worker)
        worker.start()

        accepted = dialog.exec() == QDialog.Accepted
        if worker.isRunning():
            worker.stop()
        if not accepted:
            return None
        brief = dialog.brief().strip()
        if not brief:
            self.chat.flash("Branch not created: the handoff brief was empty.")
            return None
        return self.create_branch(parent.id, dialog.title() or topic, brief)

    def _track(self, worker: StreamWorker) -> None:
        """Hold a reference until the thread has fully stopped.

        Dropping the last reference while run() is still unwinding destroys a
        running QThread, which aborts the process.
        """
        self._background.add(worker)

        def release(w=worker):
            w.wait()
            self._background.discard(w)

        worker.finished.connect(release)

    def idle(self) -> bool:
        return not self.workers and not self._background

    def set_model_status(self, kind: str, text: str) -> None:
        colors = {"ready": "#3a9d5d", "busy": "#e0a030", "error": "#d9534f", "info": "#8a8f98"}
        html_text = f'<span style="color:{colors[kind]}">●</span>&nbsp;{text}' if text else ""
        self.model_status = (kind, text)
        self._status_html = html_text
        self.map.set_model_status(html_text)
        self._update_chat_status()

    def _update_chat_status(self) -> None:
        """The local server's status matters in a chat only if it uses a local model."""
        if self.current_id is None or not self._exists(self.current_id):
            return
        spec = self.spec_for(self.current_id)
        if spec.is_local:
            self.chat.set_model_status(self._status_html)
        else:
            self.chat.set_model_status(f"Sent to {COMPANIES[spec.provider]}")

    def poll_model_status(self) -> None:
        state = self.server.health()
        name = ModelSpec("local", self.server.model).label if getattr(self.server, "model", None) else "Local model"
        if state == "ready":
            self.set_model_status("ready", f"{name} ready")
            self._status_timer.setInterval(5000)
            return
        self._status_timer.setInterval(1000)
        if state == "loading":
            self.set_model_status("busy", f"Loading {name}…")
        elif getattr(self.server, "missing", False):
            self.set_model_status("error", "llama-server not found")
        elif self.server.ours() and self.server.exited() is not None:
            self.set_model_status("error", "Local model stopped — see ~/Library/Logs/MindMap")
        elif self.server.ours():
            self.set_model_status("busy", f"Starting {name}…")
        else:
            self.set_model_status("error", "Local model offline")

    def closeEvent(self, event) -> None:
        self._status_timer.stop()
        if self.server is not None and hasattr(self.server, "interrupt"):
            self.server.interrupt()  # free workers waiting for a model to load
        for w in [*self.workers.values(), *self._background]:
            w.stop()
            w.wait(2000)
        super().closeEvent(event)


_DIR_NAMES = {"N": "north", "S": "south", "E": "east", "W": "west"}
