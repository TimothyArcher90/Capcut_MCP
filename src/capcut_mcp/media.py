"""Procesamiento de medios con ffmpeg: cortes, silencios, audio, reencuadre, mezcla."""

from __future__ import annotations

import re
from pathlib import Path

from . import ffmpeg as ff

Range = tuple[float, float]

# --------------------------------------------------------------------------- audio

AUDIO_PRESETS: dict[str, str] = {
    # Voz a cámara / reels: limpia graves, reduce ruido, de-esser, compresión y -14 LUFS (estándar redes)
    "voice": "highpass=f=80,lowpass=f=14000,afftdn=nf=-25,deesser=i=0.4,"
             "acompressor=threshold=-20dB:ratio=3:attack=10:release=200:makeup=2,"
             "loudnorm=I=-14:TP=-1.5:LRA=11",
    # Podcast: más compresión, -16 LUFS
    "podcast": "highpass=f=70,afftdn=nf=-28,deesser=i=0.5,"
               "acompressor=threshold=-22dB:ratio=4:attack=5:release=250:makeup=3,"
               "loudnorm=I=-16:TP=-1.5:LRA=9",
    # Ruido fuerte (exteriores, ventilador)
    "noisy": "highpass=f=100,lowpass=f=12000,afftdn=nf=-20:nt=w,anlmdn=s=7,"
             "acompressor=threshold=-20dB:ratio=3:makeup=2,loudnorm=I=-14:TP=-1.5:LRA=11",
    # Solo normalizar volumen
    "normalize": "loudnorm=I=-14:TP=-1.5:LRA=11",
    # Música: sin denoise, sólo nivel
    "music": "loudnorm=I=-14:TP=-1:LRA=14",
}


def enhance_audio(src: str | Path, dst: str | Path, preset: str = "voice", custom_filter: str | None = None) -> Path:
    """Mejora el audio. Si src es vídeo, el vídeo se copia sin recomprimir."""
    afilter = custom_filter or AUDIO_PRESETS.get(preset)
    if not afilter:
        raise ValueError(f"Preset desconocido '{preset}'. Opciones: {sorted(AUDIO_PRESETS)}")
    info = ff.probe(src)
    if not info["has_audio"]:
        raise ValueError(f"{src} no tiene pista de audio")
    dst = Path(dst)
    if info["has_video"]:
        ff.run(["-i", src, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", afilter,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst])
    else:
        codec = ["-c:a", "pcm_s16le"] if dst.suffix.lower() == ".wav" else ["-c:a", "aac", "-b:a", "192k"]
        ff.run(["-i", src, "-vn", "-af", afilter, "-ar", "48000", *codec, dst])
    return dst


def measure_loudness(src: str | Path) -> dict:
    proc = ff.run(["-i", src, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not m:
        return {}
    import json
    d = json.loads(m.group(0))
    return {"integrated_lufs": float(d["input_i"]), "true_peak_db": float(d["input_tp"]),
            "lra": float(d["input_lra"]), "threshold": float(d["input_thresh"])}


def extract_audio(src: str | Path, dst: str | Path) -> Path:
    dst = Path(dst)
    codec = ["-c:a", "pcm_s16le"] if dst.suffix.lower() == ".wav" else ["-c:a", "libmp3lame", "-q:a", "2"]
    ff.run(["-i", src, "-vn", "-ar", "48000", *codec, dst])
    return dst


# --------------------------------------------------------------------------- silencios

def detect_silences(src: str | Path, noise_db: float = -35.0, min_silence: float = 0.45) -> list[Range]:
    proc = ff.run(["-i", src, "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    duration = ff.probe(src)["duration"]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration
        out.append((max(0.0, s), e))
    return out


def keep_ranges_from_silences(duration: float, silences: list[Range], padding: float = 0.12,
                              min_keep: float = 0.25) -> list[Range]:
    """Invierte silencios en tramos a conservar, dejando 'padding' de aire en cada corte."""
    keeps: list[Range] = []
    cursor = 0.0
    for s, e in sorted(silences):
        end = min(duration, s + padding)
        if end - cursor >= min_keep:
            keeps.append((round(cursor, 3), round(end, 3)))
        cursor = max(cursor, e - padding)
    if duration - cursor >= min_keep:
        keeps.append((round(cursor, 3), round(duration, 3)))
    return merge_ranges(keeps)


def merge_ranges(ranges: list[Range], gap: float = 0.05) -> list[Range]:
    out: list[Range] = []
    for s, e in sorted(ranges):
        if out and s - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract_ranges(keeps: list[Range], removes: list[Range]) -> list[Range]:
    out = list(keeps)
    for rs, re_ in removes:
        nxt = []
        for s, e in out:
            if re_ <= s or rs >= e:
                nxt.append((s, e))
                continue
            if rs > s:
                nxt.append((s, rs))
            if re_ < e:
                nxt.append((re_, e))
        out = nxt
    return [(s, e) for s, e in out if e - s > 0.04]


def map_time(t: float, keeps: list[Range]) -> float | None:
    """Tiempo en el original -> tiempo en la línea de tiempo cortada (None si fue eliminado)."""
    offset = 0.0
    for s, e in keeps:
        if s <= t <= e:
            return offset + (t - s)
        offset += e - s
    return None


def render_ranges(src: str | Path, keeps: list[Range], dst: str | Path) -> Path:
    """Renderiza sólo los tramos indicados, concatenados (jump-cut)."""
    if not keeps:
        raise ValueError("No hay tramos que conservar")
    info = ff.probe(src)
    parts, labels = [], []
    for i, (s, e) in enumerate(keeps):
        if info["has_video"]:
            parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}]")
        if info["has_audio"]:
            parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    v, a = int(info["has_video"]), int(info["has_audio"])
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(keeps)}:v={v}:a={a}"
    maps = []
    if v:
        graph += "[vout]" if not a else "[vout][aout]"
        maps += ["-map", "[vout]"]
    else:
        graph += "[aout]"
    if a:
        maps += ["-map", "[aout]"]
    script = Path(dst).with_suffix(".filter.txt")
    script.write_text(graph, encoding="utf-8")
    try:
        enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] if v else []
        ff.run(["-i", src, "-filter_complex_script", script, *maps, *enc, "-c:a", "aac", "-b:a", "192k", dst])
    finally:
        script.unlink(missing_ok=True)
    return Path(dst)


# --------------------------------------------------------------------------- cortes

def cut(src: str | Path, start: float, end: float, dst: str | Path, reencode: bool = True) -> Path:
    if reencode:
        ff.run(["-ss", start, "-to", end, "-i", src, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", dst])
    else:
        ff.run(["-ss", start, "-to", end, "-i", src, "-c", "copy", dst])
    return Path(dst)


def concat(inputs: list[str | Path], dst: str | Path, width: int = 1080, height: int = 1920, fps: int = 30) -> Path:
    """Concatena clips normalizando resolución/fps (relleno negro si difiere el aspecto)."""
    if not inputs:
        raise ValueError("Lista vacía")
    args, parts, labels = [], [], []
    for i, p in enumerate(inputs):
        info = ff.probe(p)
        args += ["-i", p]
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{i}]"
        )
        if info["has_audio"]:
            parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={info['duration']}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(inputs)}:v=1:a=1[v][a]"
    ff.run([*args, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
            "-preset", "medium", "-c:a", "aac", "-b:a", "192k", dst])
    return Path(dst)


def change_speed(src: str | Path, factor: float, dst: str | Path) -> Path:
    if not 0.25 <= factor <= 4:
        raise ValueError("factor entre 0.25 y 4")
    info = ff.probe(src)
    atempo, f = [], factor
    while f > 2.0:
        atempo.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        atempo.append("atempo=0.5"); f /= 0.5
    atempo.append(f"atempo={f:.4f}")
    args = ["-i", src]
    if info["has_video"]:
        args += ["-filter:v", f"setpts=PTS/{factor}"]
    if info["has_audio"]:
        args += ["-filter:a", ",".join(atempo)]
    ff.run([*args, dst])
    return Path(dst)


# --------------------------------------------------------------------------- imagen

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080)}


def reframe(src: str | Path, dst: str | Path, aspect: str = "9:16", mode: str = "blur",
            focus_x: float = 0.5) -> Path:
    """Cambia el formato. mode='crop' recorta (focus_x 0..1 elige la zona), 'blur' fondo desenfocado, 'pad' barras negras."""
    w, h = ASPECTS[aspect]
    if mode == "crop":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}:(iw-{w})*{focus_x}:(ih-{h})/2,setsar=1")
        ff.run(["-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "copy", dst])
    elif mode == "pad":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        ff.run(["-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "copy", dst])
    elif mode == "blur":
        graph = (f"[0:v]split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                 f"boxblur=20:2[bg];[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
        ff.run(["-i", src, "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264",
                "-crf", "18", "-c:a", "copy", dst])
    else:
        raise ValueError("mode: crop | blur | pad")
    return Path(dst)


def thumbnail(src: str | Path, dst: str | Path, at: float = 1.0) -> Path:
    ff.run(["-ss", at, "-i", src, "-frames:v", "1", "-q:v", "2", dst])
    return Path(dst)


def contact_sheet(src: str | Path, dst: str | Path, every: float = 2.0, cols: int = 5) -> Path:
    """Mosaico de fotogramas para que Claude 'vea' el vídeo y decida cortes."""
    ff.run(["-i", src, "-vf", f"fps=1/{every},scale=320:-1,tile={cols}x{cols}", "-frames:v", "1", dst])
    return Path(dst)


# --------------------------------------------------------------------------- mezcla y subtítulos

def mix_music(video: str | Path, music: str | Path, dst: str | Path, music_db: float = -16.0,
              duck: bool = True, fade_out: float = 1.5) -> Path:
    """Añade música de fondo con ducking automático bajo la voz."""
    dur = ff.probe(video)["duration"]
    music_chain = (f"[1:a]aloop=loop=-1:size=2e9,atrim=duration={dur},volume={music_db}dB,"
                   f"afade=t=out:st={max(0, dur - fade_out)}:d={fade_out}[m]")
    if duck:
        graph = (f"{music_chain};[0:a]asplit[voice][key];"
                 f"[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
                 f"[voice][md]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        graph = f"{music_chain};[0:a][m]amix=inputs=2:duration=first:normalize=0[a]"
    ff.run(["-i", video, "-i", music, "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", dst])
    return Path(dst)


def _ffmpeg_filter_path(p: str | Path) -> str:
    s = str(Path(p).resolve()).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'")


def burn_subtitles(video: str | Path, srt: str | Path, dst: str | Path, font: str = "Arial",
                   size: int = 14, primary: str = "&H00FFFFFF", outline: int = 2, margin_v: int = 60,
                   bold: bool = True) -> Path:
    style = (f"FontName={font},FontSize={size},PrimaryColour={primary},OutlineColour=&H00000000,"
             f"BorderStyle=1,Outline={outline},Shadow=0,Alignment=2,MarginV={margin_v},Bold={-1 if bold else 0}")
    vf = f"subtitles='{_ffmpeg_filter_path(srt)}':force_style='{style}'"
    ff.run(["-i", video, "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "copy", dst])
    return Path(dst)
