# PyInstaller spec: one-folder build plus a single-file exe.
# Run from the repo root:  pyinstaller packaging/beam_check_desk.spec
import os

# The spec runs with its own directory as the working directory, so point at
# the CSV directly; collect_data_files() cannot see the package from here.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, "beam_check_desk", "data", "aisc_w_shapes.csv"), "beam_check_desk/data")]

a = Analysis(
    [os.path.join(ROOT, "beam_check_desk", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["beam_check_desk.ui.main_window"],
    excludes=["tkinter", "gi", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BeamCheckDesk",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
