"""Rutas y configuración. Todo se puede sobrescribir con variables de entorno."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def studio_root() -> Path:
    """Carpeta raíz donde se organiza todo el trabajo (por defecto D:\\CapCut_Studio)."""
    env = os.environ.get("CAPCUT_STUDIO_ROOT")
    if env:
        return Path(env).expanduser()
    if IS_WINDOWS and Path("D:/").exists():
        return Path("D:/CapCut_Studio")
    return Path.home() / "CapCut_Studio"


def drafts_dir_candidates() -> list[Path]:
    """Ubicaciones conocidas de la carpeta de borradores de CapCut.

    Son las rutas por defecto observadas en instalaciones de CapCut escritorio;
    pueden variar según versión o si el usuario cambió la ubicación en
    Ajustes > Ubicación de borradores. Por eso CAPCUT_DRAFTS_DIR tiene prioridad.
    """
    out: list[Path] = []
    env = os.environ.get("CAPCUT_DRAFTS_DIR")
    if env:
        out.append(Path(env).expanduser())
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))
        out.append(Path(local) / "CapCut/User Data/Projects/com.lveditor.draft")
        out.append(Path("D:/CapCut Drafts"))
    elif IS_MAC:
        out.append(Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft")
    return out


def drafts_dir() -> Path | None:
    for p in drafts_dir_candidates():
        if p.exists():
            return p
    return None


def capcut_exe() -> Path | None:
    env = os.environ.get("CAPCUT_EXE")
    candidates = [Path(env)] if env else []
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))
        candidates += [
            Path(local) / "CapCut/Apps/CapCut.exe",
            Path("C:/Program Files/CapCut/CapCut.exe"),
        ]
    elif IS_MAC:
        candidates.append(Path("/Applications/CapCut.app"))
    for c in candidates:
        if c.exists():
            return c
    return None


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
