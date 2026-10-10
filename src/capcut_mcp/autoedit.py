"""Pipeline de auto-edición: de vídeo en bruto a borrador de CapCut listo (y render opcional)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import media
from . import transcribe as tr
from .draft import Draft
from .ffmpeg import probe
from .workspace import Project


@dataclass
class AutoEditOptions:
    draft_name: str | None = None
    aspect: str = "9:16"
    fit: str = "fill"                  # fill (recorta para llenar) | fit (encaja)
    audio_preset: str | None = "voice"  # None = no tocar el audio
    remove_silences: bool = True
    silence_db: float = -35.0
    min_silence: float = 0.45
    padding: float = 0.12
    transcribe: bool = False
    language: str | None = None
    whisper_model: str = "small"
    remove_fillers: bool = False
    filler_words: list[str] = field(default_factory=list)
    captions: bool = True
    caption_max_words: int = 4
    caption_uppercase: bool = False
    caption_style: dict = field(default_factory=dict)
    music: str | None = None
    music_volume: float = 0.15
    hook_text: str | None = None
    hook_duration: float = 2.5
    render: bool = False
    template: str | None = None


def fill_scale(src_w: int, src_h: int, canvas_w: int, canvas_h: int, fit: str) -> float:
    if not (src_w and src_h):
        return 1.0
    a_s, a_c = src_w / src_h, canvas_w / canvas_h
    return 1.0 if fit == "fit" else round(max(a_s / a_c, a_c / a_s), 4)


def auto_edit(project: Project, source: str | Path, opts: AutoEditOptions, drafts_root: Path | None) -> dict:
    report: dict = {"steps": []}
    source = Path(source)
    if project.path not in source.resolve().parents:
        source = project.import_file(source, "raw_video")
        report["steps"].append(f"importado a {source}")
    stem = source.stem
    info = probe(source)

    # 1) audio
    working = source
    if opts.audio_preset and info["has_audio"]:
        working = media.enhance_audio(source, project.dir("processed_audio") / f"{stem}_enh.mp4", opts.audio_preset)
        report["steps"].append(f"audio mejorado ({opts.audio_preset})")

    # 2) silencios
    duration = info["duration"]
    keeps = [(0.0, duration)]
    if opts.remove_silences and info["has_audio"]:
        sil = media.detect_silences(working, opts.silence_db, opts.min_silence)
        keeps = media.keep_ranges_from_silences(duration, sil, opts.padding)
        removed = duration - sum(e - s for s, e in keeps)
        report["steps"].append(f"{len(sil)} silencios detectados, {removed:.1f}s eliminados")

    # 3) transcripción, muletillas y subtítulos
    captions: list[tr.Caption] = []
    if opts.transcribe and info["has_audio"]:
        words, lang = tr.transcribe(working, opts.language, opts.whisper_model)
        tr.save_words(words, project.dir("subtitles") / f"{stem}.words.json")
        report["language"] = lang
        if opts.remove_fillers:
            fillers = tr.find_fillers(words, lang, opts.filler_words)
            keeps = media.subtract_ranges(keeps, fillers)
            report["steps"].append(f"{len(fillers)} muletillas eliminadas")
        if opts.captions:
            raw_caps = tr.group_captions(words, opts.caption_max_words, uppercase=opts.caption_uppercase)
            tr.write_srt(raw_caps, project.dir("subtitles") / f"{stem}.original.srt")
            captions = tr.remap_captions(raw_caps, keeps)
            srt = tr.write_srt(captions, project.dir("subtitles") / f"{stem}.srt")
            report["srt"] = str(srt)
            report["steps"].append(f"{len(captions)} subtítulos generados")

    new_duration = sum(e - s for s, e in keeps)
    report["keep_ranges"] = keeps
    report["duration_before"] = round(duration, 2)
    report["duration_after"] = round(new_duration, 2)

    # 4) borrador CapCut
    name = opts.draft_name or f"{project.manifest['slug']}_{stem}"
    draft = Draft.from_template(opts.template, name) if opts.template else Draft.new(name, opts.aspect)
    scale = fill_scale(info["width"], info["height"], draft.width, draft.height, opts.fit)
    draft.add_jump_cuts(working, keeps, scale=scale)
    if captions:
        draft.add_captions(captions, **opts.caption_style)
    if opts.hook_text:
        draft.add_text(opts.hook_text, 0.0, opts.hook_duration, track=1, size=11, y=0.55,
                       background="#000000")
    if opts.music:
        draft.add_audio(opts.music, start=0.0, volume=opts.music_volume, loop_to=new_duration,
                        fade_in=0.5, fade_out=1.5)
    if drafts_root:
        folder = draft.save(drafts_root, overwrite=True, backup_dir=project.dir("drafts_backup"))
        project.register_draft(name, str(folder))
        report["draft_path"] = str(folder)
        report["steps"].append(f"borrador '{name}' creado en CapCut")
    # copia de seguridad siempre dentro del proyecto
    backup = draft.save(project.dir("drafts_backup"), overwrite=True)
    report["draft_backup"] = str(backup)

    # 5) render directo (no depende de CapCut)
    if opts.render:
        cut = media.render_ranges(working, keeps, project.dir("cuts") / f"{stem}_cut.mp4")
        framed = media.reframe(cut, project.dir("reframed") / f"{stem}_{opts.aspect.replace(':', 'x')}.mp4",
                               opts.aspect, "crop" if opts.fit == "fill" else "blur")
        final = framed
        if opts.music:
            final = media.mix_music(final, opts.music, project.dir("exports") / f"{stem}_music.mp4",
                                    music_db=_vol_to_db(opts.music_volume))
        if captions:
            final = media.burn_subtitles(final, report["srt"], project.dir("exports") / f"{stem}_final.mp4")
        elif final == framed:
            final = Path(framed.replace(project.dir("exports") / f"{stem}_final.mp4"))
        report["render"] = str(final)
        report["steps"].append(f"render final en {final}")

    project.log("auto_edit", source=str(source), draft=name, steps=report["steps"])
    return report


def _vol_to_db(v: float) -> float:
    import math
    return round(20 * math.log10(max(v, 0.001)), 1)
