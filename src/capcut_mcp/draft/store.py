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


ROOT_META = "root_meta_info.json"


def register_in_root_meta(drafts_root: Path, folder: Path, meta: dict) -> str:
    """Añade/actualiza el borrador en el índice root_meta_info.json que usa CapCut para listar proyectos.

    Algunas versiones de CapCut sólo muestran los borradores que figuran en este índice. Su formato no
    está documentado, así que se CLONA una entrada existente (creada por tu propia CapCut) y sólo se
    sustituyen los campos conocidos. CapCut debe estar cerrado: al salir reescribe este archivo.
    """
    import shutil
    import time

    idx_path = Path(drafts_root) / ROOT_META
    if not idx_path.exists():
        return "sin_indice"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "indice_ilegible"
    store_key = next((k for k, v in idx.items() if isinstance(v, list) and k.endswith("draft_store")), None)
    if not store_key:
        return "formato_desconocido"
    store = idx[store_key]
    fold = str(folder).replace("\\", "/")
    existing = next((e for e in store if str(e.get("draft_fold_path", "")).replace("\\", "/") == fold), None)
    base = dict(existing or (store[0] if store else {}))
    content_file = next((folder / f for f in ("draft_content.json", "draft_info.json") if (folder / f).exists()), None)
    known = {
        "draft_fold_path": fold,
        "draft_id": meta.get("draft_id"),
        "draft_name": meta.get("draft_name"),
        "draft_root_path": str(drafts_root).replace("\\", "/"),
        "draft_json_file": str(content_file).replace("\\", "/") if content_file else "",
        "tm_draft_create": meta.get("tm_draft_create"),
        "tm_draft_modified": meta.get("tm_draft_modified"),
        "tm_duration": meta.get("tm_duration"),
        "draft_cover": str(folder / "draft_cover.jpg").replace("\\", "/"),
        "draft_is_invisible": False,
        "draft_is_cloud_temp_draft": False,
        "draft_cloud_last_action_download": False,
        "streaming_edit_draft_ready": True,
    }
    for k, v in known.items():
        if k in base or not store:
            base[k] = v
    for k in ("draft_fold_path", "draft_id", "draft_name", "draft_json_file", "tm_draft_modified", "tm_duration"):
        base[k] = known[k]
    shutil.copy2(idx_path, idx_path.with_name(f"{ROOT_META}.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    if existing:
        store[store.index(existing)] = base
    else:
        store.insert(0, base)
    if "draft_ids" in idx and isinstance(idx["draft_ids"], int):
        idx["draft_ids"] = len(store)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return "registrado"
