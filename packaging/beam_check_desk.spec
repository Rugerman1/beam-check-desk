# PyInstaller spec: one-folder build plus a single-file exe.
# Run from the repo root:  pyinstaller packaging/beam_check_desk.spec
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("beam_check_desk", includes=["data/*.csv"])

a = Analysis(
    ["../beam_check_desk/__main__.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=["beam_check_desk.ui.main_window"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
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
