# -*- mode: python ; coding: utf-8 -*-

import os


_src = os.path.join(SPECPATH, "src")
_assets = os.path.join(_src, "meiwatermark", "assets")


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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MeiWatermark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(_assets, "logo.ico")],
)
