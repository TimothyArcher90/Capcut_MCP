"""Estructura de carpetas profesional para cada proyecto de edición.

D:\\CapCut_Studio\\
├── _Library\\              biblioteca global reutilizable
│   ├── music\\  sfx\\  fonts\\  brand\\  templates\\  luts\\
└── Projects\\
    └── 2026-10-10_mi-reel\\
        ├── 00_Inbox\\              lo que llega sin clasificar
        ├── 01_Raw\\video  audio\\   material original (nunca se modifica)
        ├── 02_Assets\\images  broll  music  sfx  fonts  generated\\
        ├── 03_Processed\\audio  cuts  reframed\\
        ├── 04_Subtitles\\
        ├── 05_Drafts_Backup\\       copias de seguridad de los borradores de CapCut
        ├── 06_Exports\\             renders finales
        ├── 07_Thumbnails\\
        └── project.json            manifiesto + historial de operaciones
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from .config import studio_root

LIBRARY_DIRS = ["music", "sfx", "fonts", "brand", "templates", "luts"]

PROJECT_DIRS = [
    "00_Inbox",
    "01_Raw/video",
    "01_Raw/audio",
    "02_Assets/images",
    "02_Assets/broll",
    "02_Assets/music",
    "02_Assets/sfx",
    "02_Assets/fonts",
    "02_Assets/generated",
    "03_Processed/audio",
    "03_Processed/cuts",
    "03_Processed/reframed",
    "04_Subtitles",
    "05_Drafts_Backup",
    "06_Exports",
    "07_Thumbnails",
]

# categoría lógica -> subcarpeta
CATEGORIES = {
    "inbox": "00_Inbox",
    "raw_video": "01_Raw/video",
    "raw_audio": "01_Raw/audio",
    "image": "02_Assets/images",
    "broll": "02_Assets/broll",
    "music": "02_Assets/music",
    "sfx": "02_Assets/sfx",
    "font": "02_Assets/fonts",
    "generated": "02_Assets/generated",
    "processed_audio": "03_Processed/audio",
    "cuts": "03_Processed/cuts",
    "reframed": "03_Processed/reframed",
    "subtitles": "04_Subtitles",
    "drafts_backup": "05_Drafts_Backup",
    "exports": "06_Exports",
    "thumbnails": "07_Thumbnails",
}

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
FONT_EXT = {".ttf", ".otf"}
SUB_EXT = {".srt", ".vtt", ".ass"}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "proyecto"


def guess_category(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "raw_video"
    if ext in AUDIO_EXT:
        return "raw_audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in FONT_EXT:
        return "font"
    if ext in SUB_EXT:
        return "subtitles"
    return "inbox"


def init_studio(root: Path | None = None) -> Path:
    root = Path(root) if root else studio_root()
    (root / "Projects").mkdir(parents=True, exist_ok=True)
    for d in LIBRARY_DIRS:
        (root / "_Library" / d).mkdir(parents=True, exist_ok=True)
    return root


class Project:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not (self.path / "project.json").exists():
            raise FileNotFoundError(f"No es un proyecto válido: {self.path}")

    # ---------- creación / búsqueda ----------
    @classmethod
    def create(cls, name: str, *, root: Path | None = None, date: str | None = None,
               aspect: str = "9:16", notes: str = "") -> "Project":
        root = init_studio(root)
        date = date or datetime.now().strftime("%Y-%m-%d")
        folder = root / "Projects" / f"{date}_{slugify(name)}"
        if (folder / "project.json").exists():
            return cls(folder)
        for d in PROJECT_DIRS:
            (folder / d).mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "slug": slugify(name),
            "created": datetime.now().isoformat(timespec="seconds"),
            "aspect": aspect,
            "notes": notes,
            "drafts": [],
            "history": [],
        }
        (folder / "project.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return cls(folder)

    @classmethod
    def resolve(cls, ref: str, *, root: Path | None = None) -> "Project":
        """Acepta ruta absoluta, nombre de carpeta o slug (último proyecto que coincida)."""
        p = Path(ref)
        if p.is_absolute() and (p / "project.json").exists():
            return cls(p)
        root = Path(root) if root else studio_root()
        projects = root / "Projects"
        if (projects / ref / "project.json").exists():
            return cls(projects / ref)
        slug = slugify(ref)
        matches = sorted(d for d in projects.glob(f"*_{slug}*") if (d / "project.json").exists()) if projects.exists() else []
        if not matches:
            raise FileNotFoundError(f"Proyecto no encontrado: {ref}")
        return cls(matches[-1])

    @staticmethod
    def list_all(root: Path | None = None) -> list[dict]:
        root = Path(root) if root else studio_root()
        out = []
        for d in sorted((root / "Projects").glob("*")) if (root / "Projects").exists() else []:
            mf = d / "project.json"
            if mf.exists():
                m = json.loads(mf.read_text(encoding="utf-8"))
                out.append({"folder": d.name, "path": str(d), "name": m.get("name"), "drafts": m.get("drafts", [])})
        return out

    # ---------- manifiesto ----------
    @property
    def manifest(self) -> dict:
        return json.loads((self.path / "project.json").read_text(encoding="utf-8"))

    def _save_manifest(self, m: dict) -> None:
        (self.path / "project.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")

    def log(self, action: str, **details) -> None:
        m = self.manifest
        m.setdefault("history", []).append(
            {"at": datetime.now().isoformat(timespec="seconds"), "action": action, **details}
        )
        self._save_manifest(m)

    def register_draft(self, name: str, path: str) -> None:
        m = self.manifest
        drafts = [d for d in m.get("drafts", []) if d.get("name") != name]
        drafts.append({"name": name, "path": path})
        m["drafts"] = drafts
        self._save_manifest(m)

    # ---------- archivos ----------
    def dir(self, category: str) -> Path:
        if category not in CATEGORIES:
            raise ValueError(f"Categoría desconocida '{category}'. Válidas: {sorted(CATEGORIES)}")
        d = self.path / CATEGORIES[category]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def unique_path(self, category: str, filename: str) -> Path:
        target = self.dir(category) / filename
        stem, suffix, i = target.stem, target.suffix, 2
        while target.exists():
            target = target.with_name(f"{stem}_{i}{suffix}")
            i += 1
        return target

    def import_file(self, src: str | Path, category: str | None = None, *, move: bool = False) -> Path:
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(src)
        category = category or guess_category(src)
        dest = self.unique_path(category, src.name)
        (shutil.move if move else shutil.copy2)(str(src), str(dest))
        self.log("import", src=str(src), dest=str(dest), category=category)
        return dest

    def tree(self) -> dict[str, list[str]]:
        out = {}
        for cat, rel in CATEGORIES.items():
            d = self.path / rel
            files = sorted(f.name for f in d.iterdir() if f.is_file()) if d.exists() else []
            if files:
                out[rel] = files
        return out
