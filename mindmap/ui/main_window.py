"""Wires the map, chat view, store and model together."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QMainWindow, QStackedWidget

from .. import branching
from ..commands import Command, CommandError, parse, unescape
from ..layout import Point, nearest_in_direction, place_child
from ..store import Session, Store
from .brief_dialog import BriefDialog
from .chat_view import ChatView
from . import style
from .map_view import MapView
from .worker import StreamWorker

NEW_CHAT = "New chat"


class MainWindow(QMainWindow):
    def __init__(self, store: Store, client, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mind Map")
        self.resize(1200, 800)
        self.store = store
        self.client = client
        self.current_id: int | None = None
        self.partials: dict[int, str] = {}  # session id -> text streamed so far
        self.workers: dict[int, StreamWorker] = {}
        self._background: set[StreamWorker] = set()
        self.brief_dialog_factory = BriefDialog

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
        self.chat.sendRequested.connect(self.handle_input)
        self.chat.backRequested.connect(self.back_to_map)
        self.chat.branchRequested.connect(self._branch_button)
        self.chat.sessionRequested.connect(self.pivot_to)
        self.chat.navigateRequested.connect(self.navigate)

        if not self.store.sessions():
            self.store.create_session(NEW_CHAT, x=0, y=0)
        sessions = self.store.sessions()
        self.map.load(sessions)
        self.map.center_on_node(sessions[0].id)

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
    def create_root(self, x: float, y: float) -> Session:
        s = self.store.create_session(NEW_CHAT, x=x, y=y)
        self.map.add_node(s)
        self.open_session(s.id)
        return s

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
            branching.title_from_text(title), parent_id=parent_id, brief=brief, x=x, y=y
        )
        self.map.add_node(child)
        self.pivot_to(child.id)
        return child

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
        worker = StreamWorker(self.client, context)
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
        worker = StreamWorker(self.client, request, temperature=0.3)
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

    def closeEvent(self, event) -> None:
        for w in [*self.workers.values(), *self._background]:
            w.stop()
            w.wait(2000)
        super().closeEvent(event)


_DIR_NAMES = {"N": "north", "S": "south", "E": "east", "W": "west"}
