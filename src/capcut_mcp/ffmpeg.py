"""Envoltorio mínimo sobre ffmpeg/ffprobe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import ffmpeg_bin, ffprobe_bin


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", *[str(a) for a in args]]
    proc = subprocess.run(cmd, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").splitlines()[-15:])
        raise FFmpegError(f"ffmpeg falló ({proc.returncode}):\n{tail}")
    return proc


def available() -> bool:
    try:
        subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, check=True)
        subprocess.run([ffprobe_bin(), "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def probe(path: str | Path) -> dict:
    """Devuelve duración (s), resolución, fps y si tiene audio/vídeo."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe no pudo leer {path}: {proc.stderr.strip()[-300:]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0.0)
    fps = 0.0
    if v and v.get("avg_frame_rate") not in (None, "0/0"):
        num, _, den = v["avg_frame_rate"].partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    is_image = bool(v) and (
        fmt.get("format_name", "") in {"image2", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe", "gif"}
        or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    )
    return {
        "path": str(path.resolve()),
        "duration": duration,
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "fps": round(fps, 3),
        "has_video": bool(v) and not is_image,
        "has_audio": bool(a),
        "is_image": is_image,
        "video_codec": v.get("codec_name") if v else None,
        "audio_codec": a.get("codec_name") if a else None,
        "size_bytes": int(fmt.get("size") or 0),
    }
