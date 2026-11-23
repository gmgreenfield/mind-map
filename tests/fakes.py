"""Shared test doubles."""

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QDialog


class FakeBriefDialog:
    """Stands in for BriefDialog: waits for the brief, then accepts or rejects."""

    accept = True
    title_override = None

    def __init__(self, topic, parent=None):
        self.topic = topic
        self.text = ""
        self._done = False
        self._loop = QEventLoop()

    def append(self, d):
        self.text += d

    def finish(self, _full=""):
        self._done = True
        self._loop.quit()

    def fail(self, err):
        self.finish()

    def exec(self):
        if not self._done:
            QTimer.singleShot(2000, self._loop.quit)
            self._loop.exec()
        return QDialog.Accepted if self.accept else QDialog.Rejected

    def brief(self):
        return self.text

    def title(self):
        return self.title_override or self.topic
