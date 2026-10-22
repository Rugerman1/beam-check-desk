"""PySide6 main window."""

from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from .. import __version__
from ..engine import BeamCheck, run_check, summary_dict
from ..model import BeamInput, PointLoad, UniformLoad
from ..narrative import api_key, save_api_key, write_narrative
from ..plots import diagrams_png
from ..shapes import shape_labels

SUPPORTS = [
    ("Simple supports (pin / roller)", "simple"),
    ("Cantilever, fixed at left", "cantilever_left"),
    ("Cantilever, fixed at right", "cantilever_right"),
]

LOAD_COLUMNS = ["Type", "Case", "Magnitude", "Start / position (ft)", "End (ft)", "Label"]


class ExportWorker(QThread):
    done = Signal(str, str)
    failed = Signal(str)

    def __init__(self, check: BeamCheck, path: str):
        super().__init__()
        self.check = check
        self.path = path

    def run(self):
        try:
            from ..report import build_pdf

            narrative, source = write_narrative(summary_dict(self.check))
            build_pdf(self.check, narrative, source, self.path)
            self.done.emit(self.path, source)
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


def _spin(lo, hi, value, step=1.0, decimals=2, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    return s


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Beam Check Desk {__version__}")
        self.resize(1280, 820)
        self.check: BeamCheck | None = None
        self.worker: ExportWorker | None = None
        self._build_menu()
        self._build_ui()
        self._load_example()

    # ---------- layout ----------
    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        export = QAction("Export PDF calc package...", self)
        export.setShortcut("Ctrl+E")
        export.triggered.connect(self.export_pdf)
        file_menu.addAction(export)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings = self.menuBar().addMenu("&Settings")
        key_action = QAction("Claude API key...", self)
        key_action.triggered.connect(self.set_api_key)
        settings.addAction(key_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About", self)
        about.triggered.connect(self.about)
        help_menu.addAction(about)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_inputs())
        splitter.addWidget(self._build_results())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 800])
        self.setCentralWidget(splitter)

    def _build_inputs(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        meta = QGroupBox("Project")
        form = QFormLayout(meta)
        self.project = QLineEdit()
        self.member = QLineEdit()
        self.engineer = QLineEdit()
        form.addRow("Project", self.project)
        form.addRow("Member", self.member)
        form.addRow("Engineer", self.engineer)
        layout.addWidget(meta)

        beam = QGroupBox("Beam")
        form = QFormLayout(beam)
        self.shape = QComboBox()
        self.shape.setEditable(True)
        labels = shape_labels()
        self.shape.addItems(labels)
        completer = QCompleter(labels)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.shape.setCompleter(completer)
        form.addRow("W-shape", self.shape)
        self.fy = _spin(30, 100, 50, 5, 0, " ksi")
        self.e = _spin(1000, 50000, 29000, 1000, 0, " ksi")
        form.addRow("Fy", self.fy)
        form.addRow("E", self.e)
        self.length = _spin(0.5, 300, 20, 1, 2, " ft")
        self.length.valueChanged.connect(self._length_changed)
        form.addRow("Beam length", self.length)
        self.support = QComboBox()
        for label, _ in SUPPORTS:
            self.support.addItem(label)
        self.support.currentIndexChanged.connect(self._support_changed)
        form.addRow("Supports", self.support)
        self.support_a = _spin(0, 300, 0, 1, 2, " ft")
        self.support_b = _spin(0, 300, 20, 1, 2, " ft")
        form.addRow("Left support at", self.support_a)
        form.addRow("Right support at", self.support_b)
        self.lb = _spin(0, 300, 0, 1, 2, " ft")
        self.lb.setToolTip("Unbraced length of the compression flange. 0 = continuously braced.")
        form.addRow("Unbraced length Lb", self.lb)
        cb_row = QHBoxLayout()
        self.cb = _spin(0.5, 3.0, 1.0, 0.05, 2)
        self.cb_auto = QCheckBox("Compute from moment diagram")
        self.cb_auto.setToolTip("AISC Eq. F1-1 over the whole span, for a beam braced only at the supports.")
        self.cb_auto.toggled.connect(lambda on: self.cb.setEnabled(not on))
        cb_row.addWidget(self.cb)
        cb_row.addWidget(self.cb_auto)
        form.addRow("Cb", cb_row)
        self.method = QComboBox()
        self.method.addItems(["LRFD (1.2D + 1.6L)", "ASD (D + L)"])
        form.addRow("Method", self.method)
        self.self_weight = QCheckBox("Include beam self weight as dead load")
        self.self_weight.setChecked(True)
        form.addRow("", self.self_weight)
        defl = QHBoxLayout()
        self.live_denom = _spin(60, 1000, 360, 60, 0)
        self.total_denom = _spin(60, 1000, 240, 60, 0)
        defl.addWidget(QLabel("Live L/"))
        defl.addWidget(self.live_denom)
        defl.addWidget(QLabel("Total L/"))
        defl.addWidget(self.total_denom)
        form.addRow("Deflection limits", defl)
        layout.addWidget(beam)

        loads = QGroupBox("Loads (downward positive)")
        v = QVBoxLayout(loads)
        self.loads = QTableWidget(0, len(LOAD_COLUMNS))
        self.loads.setHorizontalHeaderLabels(LOAD_COLUMNS)
        self.loads.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.loads.verticalHeader().setVisible(False)
        v.addWidget(self.loads)
        buttons = QHBoxLayout()
        add_point = QPushButton("Add point load")
        add_point.clicked.connect(lambda: self._add_load_row("Point", "L", 10, 10, "", ""))
        add_uniform = QPushButton("Add uniform load")
        add_uniform.clicked.connect(lambda: self._add_load_row("Uniform", "D", 1, 0, self.length.value(), ""))
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_load_row)
        buttons.addWidget(add_point)
        buttons.addWidget(add_uniform)
        buttons.addWidget(remove)
        v.addLayout(buttons)
        layout.addWidget(loads)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Run check")
        self.run_btn.setDefault(True)
        self.run_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.run_btn.clicked.connect(self.run)
        self.export_btn = QPushButton("Export PDF calc package")
        self.export_btn.clicked.connect(self.export_pdf)
        self.export_btn.setEnabled(False)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.export_btn)
        layout.addLayout(run_row)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(460)
        return scroll

    def _build_results(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.verdict = QLabel("Enter the beam and press Run check.")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        self.verdict.setFont(f)
        self.verdict.setWordWrap(True)
        layout.addWidget(self.verdict)

        self.checks = QTableWidget(0, 5)
        self.checks.setHorizontalHeaderLabels(["Check", "Demand", "Capacity", "Ratio", "Status"])
        self.checks.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.checks.verticalHeader().setVisible(False)
        self.checks.setEditTriggers(QTableWidget.NoEditTriggers)
        self.checks.setMaximumHeight(170)
        layout.addWidget(self.checks)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)

        self.diagram = QLabel("")
        self.diagram.setAlignment(Qt.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidget(self.diagram)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        return panel

    # ---------- helpers ----------
    def _load_example(self):
        self.project.setText("Example")
        self.member.setText("B-1")
        self.shape.setCurrentText("W18X50")
        self.length.setValue(24)
        self.support_b.setValue(24)
        self._add_load_row("Uniform", "D", 0.5, 0, 24, "Slab + deck")
        self._add_load_row("Uniform", "L", 1.0, 0, 24, "Office live")
        self._add_load_row("Point", "L", 8, 12, "", "Girder")

    def _length_changed(self, value):
        if self.support_b.value() > value or self.support_b.value() == self._last_length:
            self.support_b.setValue(value)
        self._last_length = value

    _last_length = 20.0

    def _support_changed(self, idx):
        simple = SUPPORTS[idx][1] == "simple"
        self.support_a.setEnabled(simple)
        self.support_b.setEnabled(simple)

    def _add_load_row(self, kind, case, magnitude, start, end, label):
        r = self.loads.rowCount()
        self.loads.insertRow(r)
        kind_box = QComboBox()
        kind_box.addItems(["Point", "Uniform"])
        kind_box.setCurrentText(kind)
        case_box = QComboBox()
        case_box.addItems(["D", "L"])
        case_box.setCurrentText(case)
        self.loads.setCellWidget(r, 0, kind_box)
        self.loads.setCellWidget(r, 1, case_box)
        self.loads.setItem(r, 2, QTableWidgetItem(f"{magnitude:g}"))
        self.loads.setItem(r, 3, QTableWidgetItem(f"{start:g}"))
        self.loads.setItem(r, 4, QTableWidgetItem("" if end == "" else f"{end:g}"))
        self.loads.setItem(r, 5, QTableWidgetItem(label))

    def _remove_load_row(self):
        rows = sorted({i.row() for i in self.loads.selectedIndexes()}, reverse=True)
        for r in rows:
            self.loads.removeRow(r)

    def _cell(self, r, c, default=0.0) -> float:
        item = self.loads.item(r, c)
        text = item.text().strip() if item else ""
        if not text:
            return default
        return float(text)

    def read_inputs(self) -> BeamInput:
        points, uniforms = [], []
        for r in range(self.loads.rowCount()):
            kind = self.loads.cellWidget(r, 0).currentText()
            case = self.loads.cellWidget(r, 1).currentText()
            mag = self._cell(r, 2)
            start = self._cell(r, 3)
            label_item = self.loads.item(r, 5)
            label = label_item.text() if label_item else ""
            if kind == "Point":
                points.append(PointLoad(mag, start, case, label))
            else:
                end = self._cell(r, 4, self.length.value())
                uniforms.append(UniformLoad(mag, start, end, case, label))
        return BeamInput(
            shape=self.shape.currentText(),
            length=self.length.value(),
            support=SUPPORTS[self.support.currentIndex()][1],
            support_a=self.support_a.value(),
            support_b=self.support_b.value(),
            fy=self.fy.value(),
            e=self.e.value(),
            lb=self.lb.value(),
            cb=self.cb.value(),
            method="LRFD" if self.method.currentIndex() == 0 else "ASD",
            include_self_weight=self.self_weight.isChecked(),
            live_defl_denominator=self.live_denom.value(),
            total_defl_denominator=self.total_denom.value(),
            point_loads=points,
            uniform_loads=uniforms,
            project=self.project.text(),
            member=self.member.text(),
            engineer=self.engineer.text(),
        )

    # ---------- actions ----------
    def run(self):
        try:
            beam = self.read_inputs()
            self.check = run_check(beam, compute_cb_from_diagram=self.cb_auto.isChecked())
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Check the inputs", str(exc))
            return
        self.show_results(self.check)
        self.export_btn.setEnabled(True)

    def show_results(self, check: BeamCheck):
        g = check.governing
        if check.passes:
            self.verdict.setText(f"{check.shape.label} PASSES. Governing: {g.name}, ratio {g.ratio:.3f}.")
            self.verdict.setStyleSheet("color: #1a7f37;")
        else:
            self.verdict.setText(f"{check.shape.label} DOES NOT PASS. Governing: {g.name}, ratio {g.ratio:.3f}.")
            self.verdict.setStyleSheet("color: #b42318;")
        self.checks.setRowCount(0)
        for c in check.lines:
            r = self.checks.rowCount()
            self.checks.insertRow(r)
            cells = [c.name, f"{c.demand:.3f} {c.unit}", f"{c.capacity:.3f} {c.unit}", f"{c.ratio:.3f}", c.status]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 4:
                    item.setForeground(QColor("#1a7f37" if c.status == "OK" else "#b42318"))
                self.checks.setItem(r, col, item)
        f = check.flexure
        rx = check.strength.reactions
        lines = [
            f"Reactions ({check.strength_combo}): "
            + ", ".join(f"{r:.2f} kips at {p:g} ft" for p, r in zip(rx.positions, rx.forces))
            + (f"; fixed-end moment {rx.fixed_moment:.2f} kip-ft" if check.beam.support != "simple" else ""),
            f"Mu = {check.strength.m_max:.2f} kip-ft at {check.strength.x_at_m_max:.2f} ft, "
            f"Vu = {check.strength.v_max:.2f} kips",
            f"Mp = {f.mp / 12:.1f} kip-ft, Lp = {f.lp / 12:.2f} ft, Lr = {f.lr / 12:.2f} ft, "
            f"Lb = {check.beam.lb:g} ft, Cb = {f.cb:.2f}; Mn = {f.mn / 12:.1f} kip-ft ({f.governing})",
            f"Flange {f.flange_class}, web {f.web_class}. Vn = {check.shear.vn:.1f} kips "
            f"(Cv1 = {check.shear.cv1:.3f}, phi_v = {check.shear.phi:.2f})",
        ]
        for w in check.warnings:
            lines.append("WARNING: " + w)
        self.details.setPlainText("\n".join(lines))
        pix = QPixmap()
        pix.loadFromData(diagrams_png(check, width_in=7.0, dpi=85))
        self.diagram.setPixmap(pix)

    def export_pdf(self):
        if self.check is None:
            self.run()
            if self.check is None:
                return
        default = f"{self.check.shape.label}_{self.check.beam.member or 'beam'}_check.pdf".replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(self, "Save calc package", default, "PDF files (*.pdf)")
        if not path:
            return
        self.export_btn.setEnabled(False)
        self.export_btn.setText("Writing PDF" + (" (asking Claude for the narrative)..." if api_key() else "..."))
        self.worker = ExportWorker(self.check, path)
        self.worker.done.connect(self._export_done)
        self.worker.failed.connect(self._export_failed)
        self.worker.start()

    def _export_done(self, path, source):
        self.export_btn.setEnabled(True)
        self.export_btn.setText("Export PDF calc package")
        note = "Narrative written by Claude." if source == "claude" else (
            "Narrative used the built-in template (no Claude API key set, or the request failed)."
        )
        QMessageBox.information(self, "Calc package saved", f"Saved to:\n{path}\n\n{note}")
        if sys.platform == "win32":
            try:
                os.startfile(path)  # noqa: S606
            except OSError:
                pass

    def _export_failed(self, text):
        self.export_btn.setEnabled(True)
        self.export_btn.setText("Export PDF calc package")
        QMessageBox.critical(self, "Export failed", text)

    def set_api_key(self):
        key, ok = QInputDialog.getText(
            self, "Claude API key",
            "Paste an Anthropic API key to have Claude write the calc narrative.\n"
            "Leave blank to use the built-in template. Stored in %APPDATA%\\BeamCheckDesk.",
            QLineEdit.Password, api_key() or "",
        )
        if ok:
            save_api_key(key)

    def about(self):
        QMessageBox.about(
            self, "About Beam Check Desk",
            f"<b>Beam Check Desk {__version__}</b><br>"
            "Steel W-shape beam analysis and AISC 360-22 checks (F2, F3, G2) with a PDF calc package.<br><br>"
            "Section properties from the AISC Shapes Database v16.0.<br>"
            "Student-built tool for checking hand calcs. Not for design use.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Beam Check Desk")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
