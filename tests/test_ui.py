import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_window_runs_example_and_renders(tmp_path):
    from PySide6.QtWidgets import QApplication

    from beam_check_desk.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.run()
    assert win.check is not None
    assert win.check.passes
    assert win.checks.rowCount() == 4
    assert not win.diagram.pixmap().isNull()
    win.support.setCurrentIndex(1)  # cantilever
    win.run()
    assert win.check.beam.support == "cantilever_left"
    app.processEvents()
