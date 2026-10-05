# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

import PySide6


_src = os.path.join(SPECPATH, "src")
_assets = os.path.join(_src, "meiwatermark", "assets")
_console = os.environ.get("MEIWATERMARK_BUILD_CONSOLE") == "1"


a = Analysis(
    [os.path.join(_src, "meiwatermark", "__main__.py")],
    pathex=[_src],
    binaries=[],
    datas=[(_assets, "meiwatermark/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Conda may contribute an older MSVC runtime at the bundle root. Windows loads
# it before Qt's copy, so use Qt's matching runtime consistently throughout.
_qt_dir = Path(PySide6.__file__).parent
_runtime_names = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "concrt140.dll",
}
_runtimes = {path.name.lower(): path for path in _qt_dir.glob("*.dll") if path.name.lower() in _runtime_names}
a.binaries = [
    (name, str(_runtimes.get(Path(name).name.lower(), Path(source))), kind)
    for name, source, kind in a.binaries
    # Qt uses Windows' ICU API (unsuffixed symbols). An ICU library discovered
    # on PATH, e.g. Poppler's icuuc.dll with *_78 symbols, is incompatible.
    if Path(name).name.lower() not in {"icuuc.dll", "icuin.dll"}
    and not Path(name).name.lower().startswith("icudt")
]
_root_names = {name.lower() for name, _, _ in a.binaries}
for name, source in _runtimes.items():
    if name not in _root_names:
        a.binaries.append((source.name, str(source), "BINARY"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MeiWatermark-debug" if _console else "MeiWatermark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(_assets, "logo.ico")],
)
