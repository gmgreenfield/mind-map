"""Draw the app icon (a small mind map) and write a macOS .iconset folder.

Usage: python scripts/make_icon.py OUT.iconset   (then: iconutil -c icns OUT.iconset)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

SIZES = [16, 32, 128, 256, 512]


def draw(size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 1024

    # macOS-style rounded square with a soft blue gradient.
    margin = 100 * s
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor("#5b93ff"))
    grad.setColorAt(1, QColor("#2a5fd6"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(rect, 185 * s, 185 * s)

    root = QPointF(400 * s, 512 * s)
    kids = [QPointF(690 * s, 330 * s), QPointF(720 * s, 560 * s), QPointF(560 * s, 760 * s)]
    grandkid = QPointF(840 * s, 300 * s)

    p.setPen(QPen(QColor(255, 255, 255, 200), 26 * s, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    for a, b in [(root, k) for k in kids] + [(kids[0], grandkid)]:
        path = QPainterPath(a)
        mid = (a.x() + b.x()) / 2
        path.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
        p.drawPath(path)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(root, 105 * s, 105 * s)
    for k in kids:
        p.drawEllipse(k, 62 * s, 62 * s)
    p.drawEllipse(grandkid, 40 * s, 40 * s)
    p.setBrush(QColor("#2a5fd6"))
    p.drawEllipse(root, 45 * s, 45 * s)
    p.end()
    return img


def main(out: str) -> None:
    QGuiApplication([])
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    big = draw(1024)
    for n in SIZES:
        for scale in (1, 2):
            px = n * scale
            name = f"icon_{n}x{n}{'@2x' if scale == 2 else ''}.png"
            big.scaled(px, px, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(folder / name))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/MindMap.iconset")
