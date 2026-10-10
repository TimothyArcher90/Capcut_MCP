"""Localizar y diagnosticar borradores existentes en la carpeta de CapCut."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .model import CONTENT_FILES


def _content_file(folder: Path) -> Path | None:
    for f in CONTENT_FILES:
        if (folder / f).exists():
            return folder / f
    return None


def is_readable(folder: Path) -> bool | None:
    f = _content_file(folder)
    if not f:
        return None
    try:
        json.loads(f.read_bytes().decode("utf-8"))
        return True
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def list_drafts(drafts_root: Path) -> list[dict]:
    out = []
    if not drafts_root or not drafts_root.exists():
        return out
    for d in drafts_root.iterdir():
        if not d.is_dir() or not _content_file(d):
            continue
        out.append({"name": d.name, "path": str(d),
                    "modified": datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds"),
                    "readable_json": is_readable(d)})
    return sorted(out, key=lambda x: x["modified"], reverse=True)


def find_draft(drafts_root: Path, name: str) -> Path:
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p
    cand = drafts_root / name
    if cand.exists():
        return cand
    matches = [d for d in list_drafts(drafts_root) if name.lower() in d["name"].lower()]
    if not matches:
        raise FileNotFoundError(f"Borrador '{name}' no encontrado en {drafts_root}")
    return Path(matches[0]["path"])


def doctor(drafts_root: Path | None) -> dict:
    """Comprueba si los borradores de esta instalación son JSON legible (no cifrado)."""
    if not drafts_root:
        return {"drafts_dir": None, "status": "no_encontrado",
                "hint": "Define CAPCUT_DRAFTS_DIR con la ruta de Ajustes > Borradores de CapCut."}
    drafts = list_drafts(drafts_root)
    readable = [d for d in drafts if d["readable_json"]]
    encrypted = [d for d in drafts if d["readable_json"] is False]
    status = "ok"
    if drafts and not readable:
        status = "borradores_cifrados"
    elif not drafts:
        status = "sin_borradores"
    return {"drafts_dir": str(drafts_root), "status": status, "total": len(drafts),
            "readable": len(readable), "encrypted_or_binary": len(encrypted),
            "hint": {
                "ok": "Formato legible: lectura, edición y creación de borradores disponibles.",
                "sin_borradores": "Crea un proyecto vacío en CapCut y vuelve a ejecutar el diagnóstico.",
                "borradores_cifrados": "Tu versión de CapCut cifra los borradores existentes. La CREACIÓN de "
                                       "borradores nuevos puede seguir funcionando (verifícalo con "
                                       "capcut_draft_create) pero no se pueden leer/editar los creados por "
                                       "CapCut. Alternativa garantizada: capcut_render (render directo con ffmpeg).",
            }[status]}
