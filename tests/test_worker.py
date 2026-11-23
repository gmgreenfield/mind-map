from mindmap.llm import LLMError
from mindmap.ui.worker import StreamWorker


class FakeClient:
    def __init__(self, deltas=("a", "b"), error=None):
        self.deltas = deltas
        self.error = error

    def stream_chat(self, messages, temperature=0.7):
        yield from self.deltas
        if self.error:
            raise self.error


def test_emits_tokens_then_done(qtbot):
    w = StreamWorker(FakeClient(("Hel", "lo")), [])
    tokens = []
    w.token.connect(tokens.append)
    with qtbot.waitSignal(w.done, timeout=2000) as blocker:
        w.start()
    assert blocker.args == ["Hello"]
    w.wait()
    assert tokens == ["Hel", "lo"]


def test_emits_failed_on_llm_error(qtbot):
    w = StreamWorker(FakeClient(("x",), error=LLMError("down")), [])
    with qtbot.waitSignal(w.failed, timeout=2000) as blocker:
        w.start()
    w.wait()
    assert blocker.args == ["down"]
