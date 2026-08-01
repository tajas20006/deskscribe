# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


project_root = Path(SPECPATH).parents[1]
flet_client_dir = project_root / "build" / "packaging" / "flet_client"
if not (flet_client_dir / "flet.exe").is_file():
    raise FileNotFoundError(
        "Bundled Flet client is missing. Run scripts/build_windows.ps1."
    )

os.environ["FLET_VIEW_PATH"] = str(flet_client_dir)

datas = []
binaries = []
hiddenimports = ["flet_desktop", "soundcard.mediafoundation"]

for package in ("faster_whisper", "ctranslate2"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for distribution in ("flet", "flet-desktop", "faster-whisper", "ctranslate2"):
    datas += copy_metadata(distribution)

# These paths contain user data or development-only files. Analysis only follows
# imports, so they are intentionally never added as data: models, tests, .agents,
# .venv, .uv-cache.
a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(project_root / "packaging" / "windows" / "runtime_flet.py")
    ],
    excludes=["tests"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DeskScribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
