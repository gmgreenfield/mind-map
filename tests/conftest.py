import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _main_thread_gc(qapp):
    """Same rule as the app: never let garbage collection run on a reply thread."""
    from mindmap.ui import gc_guard

    gc_guard.install(qapp)
