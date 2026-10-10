"""Servidor MCP: expone a Claude todas las operaciones de edición para CapCut."""

from __future__ import annotations

import json
from pathlib import Path

try:  # mcp >= 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

from . import assets, media
from . import capcut_app as app_ctl
from . import transcribe as tr
from .autoedit import AutoEditOptions, auto_edit
from .config import capcut_exe, drafts_dir, studio_root
from .draft import Draft, doctor, find_draft, list_drafts
from .ffmpeg import available as ffmpeg_available
from .ffmpeg import probe
from .workspace import CATEGORIES, Project, init_studio

GUIDE_PATH = Path(__file__).parent / "guide.md"

INSTRUCTIONS = """\
Eres el editor de vídeo del usuario y operas CapCut escritorio a través de este servidor.
Flujo recomendado:
1. capcut_status para ver qué está disponible (ffmpeg, carpeta de borradores, si están cifrados).
2. capcut_project_create (o capcut_project_list) -> todo se guarda organizado en el workspace (D:\\CapCut_Studio).
3. Trae material: capcut_import (rutas locales), capcut_download (URLs), capcut_save_generated (SVG/SRT/texto
   que generes tú), capcut_title_card (PNG de texto).
4. Edita: capcut_auto_edit hace el 90%% (mejora audio, quita silencios/muletillas, subtítulos, música, borrador
   en CapCut y render opcional). Para control fino usa las herramientas de media y de borrador.
5. Revisa con capcut_draft_inspect / capcut_contact_sheet y ajusta.
Tiempos SIEMPRE en segundos. Posiciones de texto: y=-0.6 tercio inferior, y=0.55 parte superior.
CapCut debe estar cerrado (o reiniciarse con capcut_app action=restart) para que vea borradores nuevos.
Lee el recurso capcut://guide para el mapa completo de funciones de CapCut y qué se automatiza.
"""

mcp = _Server("capcut", instructions=INSTRUCTIONS)


def _ok(**kw) -> str:
    return json.dumps({"ok": True, **kw}, ensure_ascii=False, indent=1, default=str)


def _project(ref: str) -> Project:
    return Project.resolve(ref)


def _drafts_root() -> Path:
    d = drafts_dir()
    if not d:
        raise RuntimeError("No encuentro la carpeta de borradores de CapCut. Define CAPCUT_DRAFTS_DIR.")
    return d


def _backup_dir(draft_folder: Path) -> Path:
    """Copias de seguridad fuera de la carpeta de borradores para no ensuciar la lista de CapCut."""
    d = init_studio() / "_Library" / "drafts_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(project: Project, category: str, src: str | Path, suffix: str, ext: str | None = None) -> Path:
    src = Path(src)
    return project.unique_path(category, f"{src.stem}{suffix}{ext or src.suffix}")


# =========================================================================== estado / app

@mcp.tool()
def capcut_status() -> str:
    """Diagnóstico: ffmpeg, workspace, carpeta de borradores de CapCut, si el formato es legible, CapCut en ejecución."""
    try:
        import faster_whisper  # noqa: F401
        whisper = True
    except ImportError:
        whisper = False
    return _ok(
        ffmpeg=ffmpeg_available(), transcription=whisper, studio_root=str(studio_root()),
        capcut_exe=str(capcut_exe()) if capcut_exe() else None, capcut_running=app_ctl.is_running(),
        drafts=doctor(drafts_dir()),
    )


@mcp.tool()
def capcut_app(action: str = "launch") -> str:
    """Controla la app CapCut: action = launch | close | restart | status.
    'restart' es útil para que CapCut muestre borradores recién creados (guarda antes tu trabajo en CapCut)."""
    import time
    if action == "status":
        return _ok(running=app_ctl.is_running())
    if action == "close":
        return _ok(message=app_ctl.close())
    if action == "restart":
        app_ctl.close()
        time.sleep(3)
    return _ok(message=app_ctl.launch())


# =========================================================================== workspace

@mcp.tool()
def capcut_project_create(name: str, aspect: str = "9:16", notes: str = "") -> str:
    """Crea un proyecto con estructura profesional de carpetas en el workspace (D:\\CapCut_Studio\\Projects\\FECHA_nombre)."""
    init_studio()
    p = Project.create(name, aspect=aspect, notes=notes)
    return _ok(project=str(p.path), folders=sorted(CATEGORIES))


@mcp.tool()
def capcut_project_list() -> str:
    """Lista los proyectos del workspace."""
    return _ok(root=str(studio_root()), projects=Project.list_all())


@mcp.tool()
def capcut_project_info(project: str) -> str:
    """Muestra manifiesto, archivos por carpeta e historial de un proyecto (nombre, slug o ruta)."""
    p = _project(project)
    m = p.manifest
    return _ok(path=str(p.path), name=m["name"], drafts=m.get("drafts", []), files=p.tree(),
               history=m.get("history", [])[-25:])


@mcp.tool()
def capcut_import(project: str, paths: list[str], category: str | None = None, move: bool = False) -> str:
    """Importa archivos locales (o carpetas completas) al proyecto, clasificándolos automáticamente.
    category opcional: raw_video, raw_audio, image, broll, music, sfx, font, generated, subtitles..."""
    p = _project(project)
    out = []
    for raw in paths:
        src = Path(raw)
        files = [f for f in src.rglob("*") if f.is_file()] if src.is_dir() else [src]
        for f in files:
            out.append(str(p.import_file(f, category, move=move)))
    return _ok(imported=out)


# =========================================================================== assets

@mcp.tool()
def capcut_download(project: str, url: str, category: str | None = None, filename: str | None = None) -> str:
    """Descarga un asset desde una URL (imagen, vídeo, audio, fuente). Páginas de YouTube/TikTok/etc. usan yt-dlp.
    Usar sólo con material propio o con licencia."""
    p = _project(project)
    return _ok(file=str(assets.download(url, p, category, filename)))


@mcp.tool()
def capcut_save_generated(project: str, filename: str, content: str, category: str = "generated") -> str:
    """Guarda un asset que TÚ (Claude) generas como texto: SVG (se convierte a PNG si hay cairosvg), SRT,
    LUT .cube, guion .txt, etc. Así puedes crear gráficos, iconos, lower-thirds o subtítulos y llevarlos a CapCut."""
    p = _project(project)
    return _ok(files=[str(f) for f in assets.save_generated(p, filename, content, category)])


@mcp.tool()
def capcut_title_card(project: str, text: str, filename: str = "title.png", width: int = 1080,
                      height: int = 1920, color: str = "#FFFFFF", size: int = 110, bg: str = "#00000000",
                      box: str | None = None, font_path: str | None = None) -> str:
    """Genera un PNG con texto (transparente por defecto) para usar como título/overlay. box='#000000AA' añade caja."""
    p = _project(project)
    return _ok(file=str(assets.make_title_card(p, text, filename, width, height, bg, color, size, font_path, box)))


@mcp.tool()
def capcut_library(kind: str = "music") -> str:
    """Lista la biblioteca global reutilizable (_Library): music | sfx | fonts | brand | templates | luts."""
    return _ok(files=assets.list_library(init_studio(), kind))


# =========================================================================== análisis

@mcp.tool()
def capcut_probe(path: str) -> str:
    """Información técnica de un archivo: duración, resolución, fps, audio, códecs."""
    return _ok(**probe(path))


@mcp.tool()
def capcut_contact_sheet(project: str, source: str, every: float = 2.0) -> str:
    """Mosaico de fotogramas (cada N s) en 07_Thumbnails para revisar visualmente el vídeo y decidir cortes."""
    p = _project(project)
    dst = _out(p, "thumbnails", source, "_sheet", ".jpg")
    return _ok(file=str(media.contact_sheet(source, dst, every)))


@mcp.tool()
def capcut_thumbnail(project: str, source: str, at: float = 1.0) -> str:
    """Extrae un fotograma como imagen (miniatura/portada)."""
    p = _project(project)
    return _ok(file=str(media.thumbnail(source, _out(p, "thumbnails", source, f"_{at:.1f}s", ".jpg"), at)))


@mcp.tool()
def capcut_detect_silences(source: str, noise_db: float = -35.0, min_silence: float = 0.45,
                           padding: float = 0.12) -> str:
    """Detecta silencios y devuelve los tramos a conservar (keep_ranges) sin modificar nada."""
    sil = media.detect_silences(source, noise_db, min_silence)
    dur = probe(source)["duration"]
    keeps = media.keep_ranges_from_silences(dur, sil, padding)
    return _ok(duration=dur, silences=sil, keep_ranges=keeps, kept_seconds=round(sum(e - s for s, e in keeps), 2))


@mcp.tool()
def capcut_loudness(source: str) -> str:
    """Mide sonoridad integrada (LUFS) y pico real. Referencia redes sociales: -14 LUFS."""
    return _ok(**media.measure_loudness(source))


@mcp.tool()
def capcut_transcribe(project: str, source: str, language: str | None = None, model: str = "small",
                      max_words: int = 4, uppercase: bool = False) -> str:
    """Transcribe con faster-whisper (local). Guarda palabras con tiempos (.words.json) y SRT en 04_Subtitles.
    Devuelve el texto para que puedas proponer cortes por contenido, hooks o títulos."""
    p = _project(project)
    words, lang = tr.transcribe(source, language, model)
    stem = Path(source).stem
    wj = tr.save_words(words, p.dir("subtitles") / f"{stem}.words.json")
    caps = tr.group_captions(words, max_words, uppercase=uppercase)
    srt = tr.write_srt(caps, p.dir("subtitles") / f"{stem}.srt")
    p.log("transcribe", source=source, srt=str(srt))
    return _ok(language=lang, words_file=str(wj), srt=str(srt), captions=len(caps),
               text=" ".join(w.text for w in words))


@mcp.tool()
def capcut_find_fillers(words_file: str, language: str = "es", extra: list[str] | None = None) -> str:
    """Encuentra muletillas ('eh', 'o sea', 'um'...) en un .words.json y devuelve sus rangos para eliminarlos."""
    words = tr.load_words(words_file)
    return _ok(ranges=tr.find_fillers(words, language, extra))


# =========================================================================== edición de medios (ffmpeg)

@mcp.tool()
def capcut_enhance_audio(project: str, source: str, preset: str = "voice", custom_filter: str | None = None) -> str:
    """Mejora de audio: presets voice | podcast | noisy | normalize | music (denoise, EQ, de-esser, compresión,
    -14 LUFS). Si es vídeo, la imagen no se recomprime. custom_filter acepta una cadena -af de ffmpeg."""
    p = _project(project)
    dst = _out(p, "processed_audio", source, f"_{preset}")
    return _ok(file=str(media.enhance_audio(source, dst, preset, custom_filter)))


@mcp.tool()
def capcut_remove_silences(project: str, source: str, noise_db: float = -35.0, min_silence: float = 0.45,
                           padding: float = 0.12, extra_remove: list[list[float]] | None = None) -> str:
    """Render con jump-cuts: elimina silencios (y rangos extra [[inicio,fin],...]) y guarda en 03_Processed/cuts."""
    p = _project(project)
    dur = probe(source)["duration"]
    keeps = media.keep_ranges_from_silences(dur, media.detect_silences(source, noise_db, min_silence), padding)
    if extra_remove:
        keeps = media.subtract_ranges(keeps, [tuple(r) for r in extra_remove])
    dst = media.render_ranges(source, keeps, _out(p, "cuts", source, "_jumpcut", ".mp4"))
    return _ok(file=str(dst), keep_ranges=keeps, before=dur, after=round(sum(e - s for s, e in keeps), 2))


@mcp.tool()
def capcut_cut(project: str, source: str, ranges: list[list[float]], join: bool = True) -> str:
    """Corta tramos [[inicio,fin],...] en segundos. join=True los une en un solo archivo; False los guarda por separado."""
    p = _project(project)
    rs = [(float(a), float(b)) for a, b in ranges]
    if join:
        return _ok(file=str(media.render_ranges(source, rs, _out(p, "cuts", source, "_edit", ".mp4"))))
    files = [str(media.cut(source, a, b, _out(p, "cuts", source, f"_{a:.1f}-{b:.1f}", ".mp4"))) for a, b in rs]
    return _ok(files=files)


@mcp.tool()
def capcut_concat(project: str, sources: list[str], aspect: str = "9:16", fps: int = 30,
                  filename: str = "concat.mp4") -> str:
    """Une varios clips en orden, normalizando resolución y fps."""
    p = _project(project)
    w, h = media.ASPECTS[aspect]
    return _ok(file=str(media.concat(sources, p.unique_path("cuts", filename), w, h, fps)))


@mcp.tool()
def capcut_reframe(project: str, source: str, aspect: str = "9:16", mode: str = "blur", focus_x: float = 0.5) -> str:
    """Cambia formato (9:16, 16:9, 1:1, 4:5). mode: crop (recorta; focus_x 0=izq 1=der), blur (fondo desenfocado), pad."""
    p = _project(project)
    dst = _out(p, "reframed", source, f"_{aspect.replace(':', 'x')}_{mode}", ".mp4")
    return _ok(file=str(media.reframe(source, dst, aspect, mode, focus_x)))


@mcp.tool()
def capcut_speed(project: str, source: str, factor: float) -> str:
    """Cambia velocidad (0.25x–4x) manteniendo el tono del audio."""
    p = _project(project)
    return _ok(file=str(media.change_speed(source, factor, _out(p, "cuts", source, f"_x{factor}"))))


@mcp.tool()
def capcut_extract_audio(project: str, source: str, fmt: str = "wav") -> str:
    """Extrae el audio de un vídeo (wav o mp3)."""
    p = _project(project)
    return _ok(file=str(media.extract_audio(source, _out(p, "raw_audio", source, "", f".{fmt}"))))


@mcp.tool()
def capcut_mix_music(project: str, video: str, music: str, music_db: float = -16.0, duck: bool = True) -> str:
    """Añade música de fondo en bucle con ducking automático bajo la voz y fade-out final (render)."""
    p = _project(project)
    return _ok(file=str(media.mix_music(video, music, _out(p, "exports", video, "_music", ".mp4"), music_db, duck)))


@mcp.tool()
def capcut_burn_subtitles(project: str, video: str, srt: str, font: str = "Arial", size: int = 14,
                          margin_v: int = 60) -> str:
    """Quema subtítulos SRT en el vídeo (render final, no editable). Para editables usa capcut_draft_add_captions."""
    p = _project(project)
    dst = _out(p, "exports", video, "_subs", ".mp4")
    return _ok(file=str(media.burn_subtitles(video, srt, dst, font, size, margin_v=margin_v)))


# =========================================================================== borradores CapCut

@mcp.tool()
def capcut_draft_list() -> str:
    """Lista los borradores de CapCut (más recientes primero) e indica si su JSON es legible."""
    root = drafts_dir()
    return _ok(drafts_dir=str(root) if root else None, drafts=list_drafts(root) if root else [])


@mcp.tool()
def capcut_draft_inspect(draft: str) -> str:
    """Muestra la línea de tiempo de un borrador: pistas, segmentos, tiempos, archivos y textos."""
    return _ok(**Draft.load(find_draft(_drafts_root(), draft)).summary())


@mcp.tool()
def capcut_draft_create(name: str, timeline: dict, project: str | None = None, template: str | None = None,
                        overwrite: bool = False) -> str:
    """Crea un borrador de CapCut desde una especificación declarativa. Ejemplo de timeline:
    {
      "canvas": "9:16", "fps": 30,
      "video":   [{"path": "D:/.../a.mp4", "in": 0, "out": 5, "scale": 1.0},
                  {"path": "D:/.../foto.png", "duration": 3}],          # se colocan en secuencia
      "overlay": [{"path": "D:/.../logo.png", "start": 0, "duration": 5, "scale": 0.3, "x": 0.7, "y": 0.8}],
      "audio":   [{"path": "D:/.../musica.mp3", "start": 0, "volume": 0.2, "loop": true, "fade_out": 1.5}],
      "texts":   [{"text": "HOOK", "start": 0, "duration": 2.5, "size": 11, "y": 0.55, "color": "#FFFF00"}],
      "srt": "D:/.../subs.srt", "caption_style": {"size": 8, "y": -0.6}
    }
    template: nombre de un borrador vacío creado con tu CapCut (máxima compatibilidad con tu versión)."""
    root = _drafts_root()
    if template:
        d = Draft.from_template(find_draft(root, template), name)
    else:
        d = Draft.new(name, timeline.get("canvas", "9:16"), timeline.get("fps", 30))
    _apply_timeline(d, timeline)
    backup = _project(project).dir("drafts_backup") if project else None
    folder = d.save(root, overwrite=overwrite, backup_dir=backup)
    if project:
        _project(project).register_draft(name, str(folder))
    return _ok(draft=str(folder), summary=d.summary(),
               next="Abre CapCut (o capcut_app action=restart) y busca el borrador por su nombre.")


def _apply_timeline(d: Draft, tl: dict) -> None:
    for v in tl.get("video", []):
        d.add_video(v["path"], start=v.get("start"), src_in=v.get("in", 0.0), src_out=v.get("out"),
                    speed=v.get("speed", 1.0), volume=v.get("volume", 1.0), scale=v.get("scale", 1.0),
                    x=v.get("x", 0.0), y=v.get("y", 0.0), duration=v.get("duration"))
    for v in tl.get("overlay", []):
        d.add_video(v["path"], start=v.get("start", 0.0), src_in=v.get("in", 0.0), src_out=v.get("out"),
                    track=v.get("track", 1), scale=v.get("scale", 0.5), x=v.get("x", 0.0), y=v.get("y", 0.0),
                    volume=v.get("volume", 0.0), alpha=v.get("alpha", 1.0), duration=v.get("duration"))
    for a in tl.get("audio", []):
        loop_to = d.duration if a.get("loop") else None
        d.add_audio(a["path"], start=a.get("start", 0.0), src_in=a.get("in", 0.0), src_out=a.get("out"),
                    track=a.get("track", 0), volume=a.get("volume", 1.0), fade_in=a.get("fade_in", 0.0),
                    fade_out=a.get("fade_out", 0.0), loop_to=loop_to)
    for t in tl.get("texts", []):
        t = dict(t)
        d.add_text(t.pop("text"), t.pop("start"), t.pop("duration"), **t)
    if tl.get("srt"):
        d.add_captions(tr.parse_srt(tl["srt"]), track=1 if tl.get("texts") else 0, **tl.get("caption_style", {}))


@mcp.tool()
def capcut_draft_add(draft: str, timeline: dict, project: str | None = None) -> str:
    """Añade elementos (mismo formato que capcut_draft_create: video/overlay/audio/texts/srt) a un borrador
    existente. Se hace copia de seguridad antes de modificar."""
    root = _drafts_root()
    folder = find_draft(root, draft)
    d = Draft.load(folder)
    _apply_timeline(d, timeline)
    backup = _project(project).dir("drafts_backup") if project else _backup_dir(folder)
    d.save(root, overwrite=True, backup_dir=backup)
    return _ok(draft=str(folder), summary=d.summary())


@mcp.tool()
def capcut_draft_add_captions(draft: str, srt: str, size: float = 8.0, color: str = "#FFFFFF", y: float = -0.6,
                              stroke_color: str = "#000000", bold: bool = True, track: int = 0) -> str:
    """Añade subtítulos EDITABLES (pista de texto) a un borrador desde un SRT."""
    root = _drafts_root()
    folder = find_draft(root, draft)
    d = Draft.load(folder)
    n = d.add_captions(tr.parse_srt(srt), track=track, size=size, color=color, y=y,
                       stroke_color=stroke_color, bold=bold)
    d.save(root, overwrite=True, backup_dir=_backup_dir(folder))
    return _ok(captions=n, draft=str(folder))


@mcp.tool()
def capcut_draft_set_volume(draft: str, kind: str = "audio", volume: float = 0.2, track: int | None = None) -> str:
    """Ajusta el volumen de todos los segmentos de un tipo de pista (video|audio), opcionalmente sólo una pista."""
    root = _drafts_root()
    folder = find_draft(root, draft)
    d = Draft.load(folder)
    n = d.set_volume(kind, volume, track)
    d.save(root, overwrite=True, backup_dir=_backup_dir(folder))
    return _ok(segments=n)


@mcp.tool()
def capcut_draft_duplicate(draft: str, new_name: str) -> str:
    """Duplica un borrador (para versiones A/B, distintos formatos o idiomas)."""
    root = _drafts_root()
    d = Draft.load(find_draft(root, draft)).clone(new_name)
    return _ok(draft=str(d.save(root)))


# =========================================================================== automatización total

@mcp.tool()
def capcut_auto_edit(project: str, source: str, draft_name: str | None = None, aspect: str = "9:16",
                     fit: str = "fill", audio_preset: str | None = "voice", remove_silences: bool = True,
                     silence_db: float = -35.0, min_silence: float = 0.45, padding: float = 0.12,
                     transcribe: bool = True, language: str | None = None, whisper_model: str = "small",
                     remove_fillers: bool = True, captions: bool = True, caption_max_words: int = 4,
                     caption_uppercase: bool = False, caption_style: dict | None = None,
                     music: str | None = None, music_volume: float = 0.15, hook_text: str | None = None,
                     render: bool = False, template: str | None = None) -> str:
    """EDICIÓN AUTOMÁTICA COMPLETA (≈90% del trabajo):
    importa -> mejora audio -> elimina silencios -> transcribe -> elimina muletillas -> subtítulos editables
    -> hook de texto -> música con fades -> crea el borrador en CapCut (jump-cuts no destructivos sobre el original)
    -> copia de seguridad -> render final opcional (render=True) en 06_Exports.
    Si faster-whisper no está instalado, usa transcribe=False (se omiten subtítulos y muletillas)."""
    p = _project(project)
    opts = AutoEditOptions(
        draft_name=draft_name, aspect=aspect, fit=fit, audio_preset=audio_preset,
        remove_silences=remove_silences, silence_db=silence_db, min_silence=min_silence, padding=padding,
        transcribe=transcribe, language=language, whisper_model=whisper_model, remove_fillers=remove_fillers,
        captions=captions, caption_max_words=caption_max_words, caption_uppercase=caption_uppercase,
        caption_style=caption_style or {}, music=music, music_volume=music_volume, hook_text=hook_text,
        render=render, template=str(find_draft(_drafts_root(), template)) if template else None,
    )
    return _ok(**auto_edit(p, source, opts, drafts_dir()))


# =========================================================================== recursos

@mcp.resource("capcut://guide")
def guide() -> str:
    """Mapa de funciones de CapCut y cómo se automatiza cada una con este servidor."""
    return GUIDE_PATH.read_text(encoding="utf-8")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
