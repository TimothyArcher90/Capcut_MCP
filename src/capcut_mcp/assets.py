"""Obtener y crear assets: descargas, archivos generados por Claude, tarjetas de título."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .workspace import Project, guess_category

PAGE_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "vimeo.com", "x.com", "twitter.com",
              "facebook.com")


def _filename_from(url: str, resp: httpx.Response | None = None) -> str:
    if resp is not None:
        cd = resp.headers.get("content-disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
        if m:
            return unquote(m.group(1))
    name = Path(unquote(urlparse(url).path)).name
    return name or "asset.bin"


def download(url: str, project: Project, category: str | None = None, filename: str | None = None) -> Path:
    """Descarga un archivo directo. Para páginas de vídeo (YouTube, TikTok...) usa yt-dlp si está instalado.

    Respeta derechos de autor y términos de cada plataforma: descarga sólo material propio o con licencia.
    """
    host = urlparse(url).netloc.lower()
    if any(h in host for h in PAGE_HOSTS):
        return _download_with_ytdlp(url, project, category or "broll")
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            name = filename or _filename_from(url, resp)
            if "." not in name:
                ctype = resp.headers.get("content-type", "").split(";")[0]
                ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4",
                       "audio/mpeg": ".mp3", "audio/wav": ".wav", "image/svg+xml": ".svg"}.get(ctype, "")
                name += ext
            dest = project.unique_path(category or guess_category(name), name)
            with open(dest, "wb") as fh:
                for chunk in resp.iter_bytes(1 << 16):
                    fh.write(chunk)
    project.log("download", url=url, dest=str(dest))
    return dest


def _download_with_ytdlp(url: str, project: Project, category: str) -> Path:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError("Para descargar desde páginas de vídeo instala yt-dlp: pip install \"capcut-mcp[extras]\"")
    out_dir = project.dir(category)
    proc = subprocess.run(
        [exe, "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", str(out_dir / "%(title).80s.%(ext)s"),
         "--print", "after_move:filepath", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp falló: {proc.stderr[-400:]}")
    dest = Path(proc.stdout.strip().splitlines()[-1])
    project.log("download", url=url, dest=str(dest), via="yt-dlp")
    return dest


def save_generated(project: Project, filename: str, content: str, category: str = "generated",
                   render_png: bool = True, png_width: int = 1080) -> list[Path]:
    """Guarda contenido de texto generado por Claude (SVG, SRT, LUT .cube, guion...).

    Si es SVG y cairosvg está instalado, también lo rasteriza a PNG (CapCut importa PNG con transparencia).
    """
    dest = project.unique_path(category, filename)
    dest.write_text(content, encoding="utf-8")
    out = [dest]
    if dest.suffix.lower() == ".svg" and render_png:
        try:
            import cairosvg  # type: ignore
            png = dest.with_suffix(".png")
            cairosvg.svg2png(url=str(dest), write_to=str(png), output_width=png_width)
            out.append(png)
        except ImportError:
            pass
    project.log("generated_asset", files=[str(p) for p in out])
    return out


def _hex(c: str) -> tuple[int, int, int, int]:
    c = c.lstrip("#")
    if len(c) == 6:
        c += "ff"
    return tuple(int(c[i:i + 2], 16) for i in range(0, 8, 2))  # type: ignore


def _font(size: int, font_path: str | None):
    from PIL import ImageFont
    candidates = [font_path] if font_path else []
    candidates += ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for c in candidates:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size=size)


def make_title_card(project: Project, text: str, filename: str = "title.png", width: int = 1080,
                    height: int = 1920, bg: str = "#00000000", color: str = "#FFFFFF", size: int = 110,
                    font_path: str | None = None, box: str | None = None, padding: int = 40) -> Path:
    """PNG con texto centrado (fondo transparente por defecto) para usar como overlay en CapCut."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (width, height), _hex(bg))
    draw = ImageDraw.Draw(img)
    font = _font(size, font_path)
    # ajuste de líneas
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) > width - 2 * padding and cur:
            lines.append(cur); cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    line_h = int(size * 1.2)
    total_h = line_h * len(lines)
    y = (height - total_h) // 2
    if box:
        maxw = max(draw.textlength(l, font=font) for l in lines)
        draw.rounded_rectangle([(width - maxw) / 2 - padding, y - padding, (width + maxw) / 2 + padding,
                                y + total_h + padding], radius=30, fill=_hex(box))
    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(((width - lw) / 2, y), line, font=font, fill=_hex(color),
                  stroke_width=max(2, size // 25), stroke_fill=(0, 0, 0, 255))
        y += line_h
    dest = project.unique_path("generated", filename)
    img.save(dest)
    project.log("title_card", text=text, dest=str(dest))
    return dest


def list_library(root: Path, kind: str) -> list[str]:
    d = root / "_Library" / kind
    return sorted(str(p) for p in d.rglob("*") if p.is_file()) if d.exists() else []
