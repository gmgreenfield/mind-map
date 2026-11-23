import gc

from mindmap.ui import gc_guard


def test_automatic_gc_is_off_and_collected_on_timer(qapp, qtbot):
    guard = gc_guard.install(qapp)
    assert gc_guard.install(qapp) is guard
    assert not gc.isenabled()

    class Cycle:
        pass

    for _ in range(guard.thresholds[0] * 3):
        a, b = Cycle(), Cycle()
        a.b, b.a = b, a
    del a, b
    qtbot.waitUntil(lambda: gc.get_count()[0] <= guard.thresholds[0], timeout=3000)
