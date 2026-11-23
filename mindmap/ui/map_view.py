"""The mind map: a pannable, zoomable canvas of session nodes."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
)

from ..store import Session
from . import style

NODE_W, NODE_H = 200.0, 64.0
MIN_SCALE, MAX_SCALE = 0.15, 3.0


def is_dark(widget) -> bool:
    return widget.palette().window().color().lightness() < 128


class Theme:
    """QColor view of the shared palette, for painting."""

    def __init__(self, dark: bool):
        p = style.DARK if dark else style.LIGHT
        self.bg = QColor(p.bg)
        self.grid = QColor(p.grid)
        self.node = QColor(p.surface if not dark else p.assistant_bubble)
        self.node_border = QColor(p.node_border)
        self.text = QColor(p.text)
        self.subtext = QColor(p.subtext)
        self.edge = QColor(p.edge)
        self.accent = QColor(p.accent)
        self.busy = QColor(p.busy)


class NodeItem(QGraphicsObject):
    def __init__(self, session: Session, view: "MapView"):
        super().__init__()
        self.session_id = session.id
        self.parent_id = session.parent_id
        self.title = session.title
        self.is_branch = session.brief is not None
        self.view = view
        self.current = False
        self.busy = False
        self.setPos(session.x, session.y)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(1)
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._dragged = False
        self._subtree = True

    def boundingRect(self) -> QRectF:
        return QRectF(-NODE_W / 2 - 4, -NODE_H / 2 - 4, NODE_W + 8, NODE_H + 8)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        t = self.view.theme
        rect = QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)
        painter.setRenderHint(QPainter.Antialiasing)
        border = t.accent if self.current else (t.busy if self.busy else t.node_border)
        painter.setPen(QPen(border, 2.5 if self.current else 1.2))
        painter.setBrush(QBrush(t.node))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setPen(t.text)
        f = QFont()
        f.setPointSizeF(12.5)
        f.setWeight(QFont.DemiBold)
        painter.setFont(f)
        text_rect = rect.adjusted(14, 10, -14, -26)
        title = painter.fontMetrics().elidedText(self.title, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        f.setPointSizeF(10)
        f.setWeight(QFont.Normal)
        painter.setFont(f)
        painter.setPen(t.subtext)
        sub = "thinking…" if self.busy else ("branch" if self.is_branch else "root")
        painter.drawText(rect.adjusted(14, 34, -14, -8), Qt.AlignLeft | Qt.AlignVCenter, sub)

    # --- interaction ----------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        self._press = self._last = event.scenePos()
        self._dragged = False
        self._subtree = not (event.modifiers() & Qt.AltModifier)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        if not self._dragged and (event.scenePos() - self._press).manhattanLength() < 4:
            return
        self._dragged = True
        delta = event.scenePos() - self._last
        self._last = event.scenePos()
        self.view.drag_nodes(self.session_id, delta.x(), delta.y(), self._subtree)

    def mouseReleaseEvent(self, event) -> None:
        if self._press is None:
            return
        if self._dragged:
            self.view.finish_drag(self.session_id, self._subtree)
        else:
            self.view.nodeActivated.emit(self.session_id)
        self._press = None


class EdgeItem(QGraphicsPathItem):
    def __init__(self, parent_node: NodeItem, child_node: NodeItem, theme: Theme):
        super().__init__()
        self.a = parent_node
        self.b = child_node
        self.setZValue(0)
        self.setPen(QPen(theme.edge, 2, Qt.SolidLine, Qt.RoundCap))
        self.update_path()

    def update_path(self) -> None:
        p1, p2 = self.a.pos(), self.b.pos()
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        path = QPainterPath(p1)
        if abs(dx) >= abs(dy):
            mid = p1.x() + dx / 2
            path.cubicTo(QPointF(mid, p1.y()), QPointF(mid, p2.y()), p2)
        else:
            mid = p1.y() + dy / 2
            path.cubicTo(QPointF(p1.x(), mid), QPointF(p2.x(), mid), p2)
        self.setPath(path)


class MapView(QGraphicsView):
    nodeActivated = Signal(int)
    nodesMoved = Signal(list)  # [(id, x, y), ...]
    createRootRequested = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = Theme(is_dark(self))
        self.animation_ms = 450
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-50_000, -50_000, 100_000, 100_000)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.nodes: dict[int, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self._anim: QVariantAnimation | None = None

        self.hint = QLabel(
            "Click a node to open · double-click empty space for a new chat · "
            "drag moves a branch (⌥ = node only) · scroll to pan · pinch or ⌘-scroll to zoom",
            self,
        )
        self.hint.setStyleSheet(
            f"color: {self.theme.subtext.name()}; background: transparent; font-size: 11px;"
        )
        self.hint.adjustSize()

    # --- model -------------------------------------------------------------
    def load(self, sessions: list[Session]) -> None:
        self._scene.clear()
        self.nodes.clear()
        self.edges.clear()
        for s in sessions:
            self._add_item(s)
        for s in sessions:
            if s.parent_id is not None:
                self._add_edge(s.parent_id, s.id)

    def add_node(self, session: Session) -> None:
        self._add_item(session)
        if session.parent_id is not None:
            self._add_edge(session.parent_id, session.id)

    def _add_item(self, s: Session) -> None:
        item = NodeItem(s, self)
        self._scene.addItem(item)
        self.nodes[s.id] = item

    def _add_edge(self, parent_id: int, child_id: int) -> None:
        if parent_id in self.nodes and child_id in self.nodes:
            edge = EdgeItem(self.nodes[parent_id], self.nodes[child_id], self.theme)
            self._scene.addItem(edge)
            self.edges.append(edge)

    def set_title(self, session_id: int, title: str) -> None:
        node = self.nodes[session_id]
        node.title = title
        node.update()

    def set_current(self, session_id: int | None) -> None:
        for sid, node in self.nodes.items():
            node.current = sid == session_id
            node.update()

    def set_busy(self, session_id: int, busy: bool) -> None:
        if session_id in self.nodes:
            self.nodes[session_id].busy = busy
            self.nodes[session_id].update()

    def subtree(self, session_id: int) -> list[int]:
        out, stack = [], [session_id]
        while stack:
            sid = stack.pop()
            out.append(sid)
            stack.extend(n.session_id for n in self.nodes.values() if n.parent_id == sid)
        return out

    # --- dragging ------------------------------------------------------------
    def drag_nodes(self, session_id: int, dx: float, dy: float, subtree: bool = True) -> None:
        ids = self.subtree(session_id) if subtree else [session_id]
        for sid in ids:
            self.nodes[sid].moveBy(dx, dy)
        for e in self.edges:
            e.update_path()

    def finish_drag(self, session_id: int, subtree: bool = True) -> None:
        ids = self.subtree(session_id) if subtree else [session_id]
        self.nodesMoved.emit([(sid, self.nodes[sid].x(), self.nodes[sid].y()) for sid in ids])

    # --- camera -------------------------------------------------------------
    def camera(self) -> tuple[QPointF, float]:
        return self.mapToScene(self.viewport().rect().center()), self.transform().m11()

    def set_camera(self, center: QPointF, scale: float) -> None:
        self.setTransform(QTransform.fromScale(scale, scale))
        self.centerOn(center)

    def fill_scale(self) -> float:
        """Scale at which a node fills the viewport (the 'zoomed in' look)."""
        vp = self.viewport().rect()
        return max(1.0, min(vp.width() / NODE_W, vp.height() / NODE_H) * 0.95)

    def animate_camera(
        self,
        center: QPointF,
        scale: float,
        on_done: Callable[[], None] | None = None,
        dip: float = 0.0,
        start: tuple[QPointF, float] | None = None,
    ) -> None:
        if self._anim is not None:
            self._anim.stop()
        c0, s0 = start or self.camera()
        if self.animation_ms <= 0:
            self.set_camera(center, scale)
            if on_done:
                on_done()
            return

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self.animation_ms)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def step(t):
            t = float(t)
            c = c0 + (center - c0) * t
            # Interpolate zoom geometrically so it feels even.
            s = s0 * (scale / s0) ** t
            s *= 1.0 - dip * math.sin(math.pi * t)
            self.set_camera(c, max(MIN_SCALE, s))

        anim.valueChanged.connect(step)
        if on_done:
            anim.finished.connect(on_done)
        self._anim = anim
        anim.start()

    def center_on_node(self, session_id: int, scale: float = 1.0) -> None:
        self.set_camera(self.nodes[session_id].pos(), scale)

    def zoom_into(self, session_id: int, on_done=None) -> None:
        self.animate_camera(self.nodes[session_id].pos(), self.fill_scale(), on_done)

    def zoom_out_from(self, session_id: int, on_done=None) -> None:
        pos = self.nodes[session_id].pos()
        self.animate_camera(pos, 1.0, on_done, start=(pos, self.fill_scale()))

    def pivot(self, from_id: int | None, to_id: int, on_done=None) -> None:
        """Slide from one zoomed-in node to another, dipping out to show the path."""
        target = self.nodes[to_id].pos()
        fill = self.fill_scale()
        if from_id is None or from_id not in self.nodes:
            self.animate_camera(target, fill, on_done)
            return
        start = (self.nodes[from_id].pos(), fill)
        dist = math.hypot(target.x() - start[0].x(), target.y() - start[0].y())
        # Dip enough that both nodes are on screen mid-flight.
        vp = self.viewport().rect()
        mid_scale = min(vp.width(), vp.height()) / max(dist + NODE_W * 2, 1)
        dip = max(0.0, min(0.95, 1.0 - mid_scale / fill))
        saved = self.animation_ms
        self.animation_ms = int(saved * 1.6) if saved > 0 else 0
        try:
            self.animate_camera(target, fill, on_done, dip=dip, start=start)
        finally:
            self.animation_ms = saved

    # --- input ----------------------------------------------------------------
    def wheelEvent(self, event) -> None:
        pixel = event.pixelDelta()
        if (event.modifiers() & Qt.ControlModifier) or pixel.isNull():
            factor = 1.0015 ** event.angleDelta().y()
            self._zoom_by(factor)
        else:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - pixel.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - pixel.y())

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.NativeGesture and event.gestureType() == Qt.ZoomNativeGesture:
            self._zoom_by(1.0 + event.value())
            return True
        return super().viewportEvent(event)

    def _zoom_by(self, factor: float) -> None:
        s = self.transform().m11()
        factor = max(MIN_SCALE / s, min(MAX_SCALE / s, factor))
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.itemAt(event.position().toPoint()) is None:
            p = self.mapToScene(event.position().toPoint())
            self.createRootRequested.emit(p.x(), p.y())
            return
        super().mouseDoubleClickEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.theme.bg)
        step = 40
        painter.setPen(QPen(self.theme.grid, 0))
        left = int(math.floor(rect.left() / step)) * step
        top = int(math.floor(rect.top() / step)) * step
        if self.transform().m11() < 0.3:
            return
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(QPointF(x, y))
                y += step
            x += step

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.hint.move(16, self.viewport().height() - self.hint.height() - 12)
