"""Generador de borradores (drafts) de CapCut escritorio.

CapCut no tiene API pública. Un proyecto de CapCut escritorio es una carpeta dentro de
la carpeta de borradores con, entre otros:

  draft_content.json   (Windows)  /  draft_info.json (algunas versiones/macOS)
  draft_meta_info.json

El formato NO está documentado oficialmente; esta implementación sigue la estructura
observada en borradores reales y en proyectos open-source que la han estudiado. Puede
cambiar entre versiones de CapCut. Para máxima compatibilidad:

  * Se escriben ambos nombres (draft_content.json y draft_info.json).
  * Se puede partir de una PLANTILLA: un borrador vacío creado por TU versión de CapCut
    (Draft.from_template), así se heredan los campos que esa versión espera.

Unidades: la API pública de esta clase usa SEGUNDOS; internamente CapCut usa MICROSEGUNDOS.
Posición: x/y en coordenadas normalizadas del lienzo (0,0 = centro; y=-0.75 cerca del borde inferior).
"""

from __future__ import annotations

import copy
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .. import ffmpeg as ff

US = 1_000_000
PHOTO_DURATION_US = 10_800 * US  # CapCut trata las imágenes como clips de 3 h recortables

CANVAS_PRESETS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350),
                  "3:4": (1080, 1440), "4:3": (1440, 1080), "21:9": (2560, 1080)}

CONTENT_FILES = ("draft_content.json", "draft_info.json")


def _id() -> str:
    return str(uuid.uuid4()).upper()


def _us(seconds: float) -> int:
    return int(round(float(seconds) * US))


def hex_to_rgb(color: str) -> list[float]:
    c = color.lstrip("#")
    return [round(int(c[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def _timerange(start_s: float, dur_s: float) -> dict:
    return {"start": _us(start_s), "duration": _us(dur_s)}


def _empty_content(width: int, height: int, fps: float, name: str) -> dict:
    now = int(time.time())
    return {
        "canvas_config": {"height": height, "ratio": "original", "width": width},
        "color_space": 0,
        "config": {
            "adjust_max_index": 1, "attachment_info": [], "combination_max_index": 1, "export_range": None,
            "extract_audio_last_index": 1, "lyrics_recognition_id": "", "lyrics_sync": True,
            "lyrics_taskinfo": [], "maintrack_adsorb": True, "material_save_mode": 0,
            "original_sound_last_index": 1, "record_audio_last_index": 1, "sticker_max_index": 1,
            "subtitle_recognition_id": "", "subtitle_sync": True, "subtitle_taskinfo": [],
            "system_font_list": [], "video_mute": False, "zoom_info_params": None,
        },
        "cover": None,
        "create_time": now,
        "duration": 0,
        "extra_info": None,
        "fps": float(fps),
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": _id(),
        "keyframe_graph_list": [],
        "keyframes": {k: [] for k in ("adjusts", "audios", "effects", "filters", "handwrites", "stickers",
                                       "texts", "videos")},
        "last_modified_platform": {"app_id": 359289, "app_source": "cc", "app_version": "", "os": "windows"},
        "materials": {k: [] for k in (
            "ai_translates", "audio_balances", "audio_effects", "audio_fades", "audio_track_indexes", "audios",
            "beats", "canvases", "chromas", "color_curves", "digital_humans", "drafts", "effects", "flowers",
            "green_screens", "handwrites", "hsl", "images", "log_color_wheels", "loudnesses", "manual_deformations",
            "masks", "material_animations", "material_colors", "multi_language_refs", "placeholders",
            "plugin_effects", "primary_color_wheels", "realtime_denoises", "shapes", "smart_crops",
            "smart_relights", "sound_channel_mappings", "speeds", "stickers", "tail_leaders", "text_templates",
            "texts", "time_marks", "transitions", "video_effects", "video_trackings", "videos",
            "vocal_beautifys", "vocal_separations")},
        "mutable_config": None,
        "name": name,
        "new_version": "110.0.0",
        "platform": {"app_id": 359289, "app_source": "cc", "app_version": "", "os": "windows"},
        "relationships": [],
        "render_index_track_mode_on": False,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "update_time": now,
        "version": 360000,
    }


class Draft:
    """Borrador de CapCut construible por código."""

    def __init__(self, name: str, width: int = 1080, height: int = 1920, fps: float = 30.0,
                 content: dict | None = None):
        self.name = name
        self.content = content or _empty_content(width, height, fps, name)
        self.content.setdefault("materials", {})
        self.content.setdefault("tracks", [])
        self._probe_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------ constructores
    @classmethod
    def new(cls, name: str, canvas: str | tuple[int, int] = "9:16", fps: float = 30.0) -> "Draft":
        w, h = CANVAS_PRESETS[canvas] if isinstance(canvas, str) else canvas
        return cls(name, w, h, fps)

    @classmethod
    def load(cls, folder: str | Path) -> "Draft":
        folder = Path(folder)
        for fname in CONTENT_FILES:
            f = folder / fname
            if f.exists():
                raw = f.read_bytes()
                try:
                    content = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise ValueError(
                        f"{f} no es JSON legible (posiblemente cifrado por tu versión de CapCut). "
                        "Ver docs/COMPATIBILIDAD.md"
                    ) from e
                d = cls(content.get("name") or folder.name, content=content)
                d.name = folder.name
                return d
        raise FileNotFoundError(f"No hay draft_content.json/draft_info.json en {folder}")

    @classmethod
    def from_template(cls, template_folder: str | Path, name: str, clear: bool = True) -> "Draft":
        """Parte de un borrador real de tu CapCut (recomendado para compatibilidad)."""
        d = cls.load(template_folder)
        d.name = name
        d.content["name"] = name
        d.content["id"] = _id()
        if clear:
            d.content["tracks"] = []
            for k in d.content.get("materials", {}):
                if isinstance(d.content["materials"][k], list):
                    d.content["materials"][k] = []
            d.content["duration"] = 0
        return d

    # ------------------------------------------------------------------ utilidades
    @property
    def width(self) -> int:
        return self.content["canvas_config"]["width"]

    @property
    def height(self) -> int:
        return self.content["canvas_config"]["height"]

    @property
    def duration(self) -> float:
        return self.content.get("duration", 0) / US

    def _mat(self, kind: str) -> list:
        return self.content["materials"].setdefault(kind, [])

    def _probe(self, path: str) -> dict:
        if path not in self._probe_cache:
            self._probe_cache[path] = ff.probe(path)
        return self._probe_cache[path]

    def track(self, kind: str, index: int = 0, name: str = "") -> dict:
        """Devuelve (creando si hace falta) la pista nº index del tipo dado (video|audio|text|effect|sticker)."""
        same = [t for t in self.content["tracks"] if t["type"] == kind]
        while len(same) <= index:
            t = {"attribute": 0, "flag": 0, "id": _id(), "is_default_name": not name, "name": name,
                 "segments": [], "type": kind}
            self.content["tracks"].append(t)
            same.append(t)
        return same[index]

    def track_end(self, kind: str, index: int = 0) -> float:
        t = self.track(kind, index)
        if not t["segments"]:
            return 0.0
        return max(s["target_timerange"]["start"] + s["target_timerange"]["duration"] for s in t["segments"]) / US

    def _recompute_duration(self) -> None:
        end = 0
        for t in self.content["tracks"]:
            for s in t["segments"]:
                end = max(end, s["target_timerange"]["start"] + s["target_timerange"]["duration"])
        self.content["duration"] = end

    def _speed_material(self, speed: float) -> str:
        m = {"curve_speed": None, "id": _id(), "mode": 0, "speed": float(speed), "type": "speed"}
        self._mat("speeds").append(m)
        return m["id"]

    def _common_refs(self, speed: float) -> list[str]:
        refs = [self._speed_material(speed)]
        sc = {"audio_channel_mapping": 0, "id": _id(), "is_config_open": False, "type": ""}
        self._mat("sound_channel_mappings").append(sc)
        refs.append(sc["id"])
        return refs

    def _segment(self, material_id: str, start: float, dur: float, src_in: float | None, speed: float,
                 volume: float, refs: list[str], clip: dict | None, render_index: int = 0) -> dict:
        seg = {
            "caption_info": None, "cartoon": False, "clip": clip, "common_keyframes": [],
            "enable_adjust": True, "enable_color_correct_adjust": False, "enable_color_curves": True,
            "enable_color_match_adjust": False, "enable_color_wheels": True, "enable_lut": True,
            "enable_smart_color_adjust": False, "extra_material_refs": refs, "group_id": "",
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000} if clip else None,
            "id": _id(), "intensifies_audio": False, "is_placeholder": False, "is_tone_modify": False,
            "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": material_id,
            "render_index": render_index, "responsive_layout": {
                "enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "",
                "vertical_pos_layout": 0},
            "reverse": False, "source_timerange": _timerange(src_in, dur * speed) if src_in is not None else None,
            "speed": float(speed), "target_timerange": _timerange(start, dur), "template_id": "",
            "template_scene": "default", "track_attribute": 0, "track_render_index": 0,
            "uniform_scale": {"on": True, "value": 1.0} if clip else None, "visible": True,
            "volume": float(volume),
        }
        return seg

    @staticmethod
    def _clip(scale: float = 1.0, x: float = 0.0, y: float = 0.0, rotation: float = 0.0, alpha: float = 1.0,
              flip_h: bool = False) -> dict:
        return {"alpha": alpha, "flip": {"horizontal": flip_h, "vertical": False}, "rotation": rotation,
                "scale": {"x": scale, "y": scale}, "transform": {"x": x, "y": y}}

    # ------------------------------------------------------------------ vídeo / imagen
    def add_video(self, path: str | Path, start: float | None = None, src_in: float = 0.0,
                  src_out: float | None = None, track: int = 0, speed: float = 1.0, volume: float = 1.0,
                  scale: float = 1.0, x: float = 0.0, y: float = 0.0, rotation: float = 0.0,
                  alpha: float = 1.0, duration: float | None = None) -> dict:
        """Añade un vídeo o imagen. start=None lo coloca al final de la pista. Devuelve el segmento."""
        path = str(Path(path).resolve())
        info = self._probe(path)
        is_photo = info["is_image"]
        if is_photo:
            dur = duration or 3.0
            src_in, mat_dur = 0.0, PHOTO_DURATION_US
        else:
            src_out = info["duration"] if src_out is None else min(src_out, info["duration"])
            dur = (src_out - src_in) / speed
            mat_dur = _us(info["duration"])
        material = {
            "aigc_type": "none", "audio_fade": None, "category_id": "", "category_name": "local",
            "check_flag": 63487, "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                                          "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                                          "upper_right_x": 1.0, "upper_right_y": 0.0},
            "crop_ratio": "free", "crop_scale": 1.0, "duration": mat_dur, "extra_type_option": 0,
            "has_audio": bool(info["has_audio"]), "height": info["height"], "id": _id(),
            "local_material_id": "", "material_id": "", "material_name": Path(path).name, "path": path,
            "source_platform": 0, "type": "photo" if is_photo else "video", "width": info["width"],
        }
        self._mat("videos").append(material)
        refs = self._common_refs(speed)
        canvas = {"album_image": "", "blur": 0.0, "color": "", "id": _id(), "image": "", "image_id": "",
                  "image_name": "", "source_platform": 0, "team_id": "", "type": "canvas_color"}
        self._mat("canvases").append(canvas)
        refs.append(canvas["id"])
        t = self.track("video", track)
        if start is None:
            start = self.track_end("video", track)
        seg = self._segment(material["id"], start, dur, src_in, speed, volume, refs,
                            self._clip(scale, x, y, rotation, alpha), render_index=track)
        t["segments"].append(seg)
        t["segments"].sort(key=lambda s: s["target_timerange"]["start"])
        self._recompute_duration()
        return seg

    def add_jump_cuts(self, path: str | Path, keep_ranges: list[tuple[float, float]], start: float = 0.0,
                      track: int = 0, **kw) -> list[dict]:
        """Coloca los tramos conservados de un mismo archivo uno tras otro (edición no destructiva)."""
        segs, t = [], start
        for s, e in keep_ranges:
            seg = self.add_video(path, start=t, src_in=s, src_out=e, track=track, **kw)
            t += (e - s) / kw.get("speed", 1.0)
            segs.append(seg)
        return segs

    # ------------------------------------------------------------------ audio
    def add_audio(self, path: str | Path, start: float | None = None, src_in: float = 0.0,
                  src_out: float | None = None, track: int = 0, volume: float = 1.0, speed: float = 1.0,
                  fade_in: float = 0.0, fade_out: float = 0.0, loop_to: float | None = None,
                  name: str | None = None) -> list[dict]:
        """Añade audio (música, voz en off, SFX). loop_to=segundos repite el audio hasta ese punto."""
        path = str(Path(path).resolve())
        info = self._probe(path)
        src_out = info["duration"] if src_out is None else min(src_out, info["duration"])
        if start is None:
            start = self.track_end("audio", track)
        material = {"app_id": 0, "category_id": "", "category_name": "local", "check_flag": 1,
                    "duration": _us(info["duration"]), "effect_id": "", "formula_id": "", "id": _id(),
                    "intensifies_path": "", "local_material_id": "", "music_id": _id(),
                    "name": name or Path(path).name, "path": path, "source_platform": 0, "team_id": "",
                    "text_id": "", "tone_category_id": "", "tone_effect_id": "", "tone_type": "",
                    "type": "extract_music", "video_id": "", "wave_points": []}
        self._mat("audios").append(material)
        t = self.track("audio", track)
        segs = []
        cursor, end_target = start, loop_to if loop_to else start + (src_out - src_in) / speed
        while cursor < end_target - 0.01:
            dur = min((src_out - src_in) / speed, end_target - cursor)
            refs = self._common_refs(speed)
            if fade_in or fade_out:
                fade = {"fade_in_duration": _us(fade_in if cursor == start else 0),
                        "fade_out_duration": _us(fade_out if cursor + dur >= end_target - 0.01 else 0),
                        "fade_type": 0, "id": _id(), "type": "audio_fade"}
                self._mat("audio_fades").append(fade)
                refs.append(fade["id"])
            seg = self._segment(material["id"], cursor, dur, src_in, speed, volume, refs, None)
            t["segments"].append(seg)
            segs.append(seg)
            cursor += dur
            if not loop_to:
                break
        t["segments"].sort(key=lambda s: s["target_timerange"]["start"])
        self._recompute_duration()
        return segs

    # ------------------------------------------------------------------ texto
    def add_text(self, text: str, start: float, duration: float, track: int = 0, size: float = 8.0,
                 color: str = "#FFFFFF", x: float = 0.0, y: float = -0.6, bold: bool = True,
                 stroke_color: str | None = "#000000", stroke_width: float = 0.08,
                 background: str | None = None, scale: float = 1.0, font_path: str = "",
                 align: int = 1, max_line_width: float = 0.82) -> dict:
        """Añade un texto/subtítulo editable en CapCut. y=-0.6 ≈ tercio inferior."""
        style: dict[str, Any] = {
            "fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0,
                                                                                  "color": hex_to_rgb(color)}}},
            "range": [0, len(text)], "size": size, "bold": bold, "italic": False, "underline": False,
            "font": {"id": "", "path": font_path},
        }
        if stroke_color:
            style["strokes"] = [{"content": {"solid": {"alpha": 1.0, "color": hex_to_rgb(stroke_color)}},
                                 "width": stroke_width}]
        material = {
            "add_type": 0, "alignment": align, "background_alpha": 1.0 if background else 0.0,
            "background_color": background or "", "background_height": 0.14, "background_horizontal_offset": 0.0,
            "background_round_radius": 0.0, "background_style": 1 if background else 0,
            "background_vertical_offset": 0.0, "background_width": 0.14, "base_content": "",
            "bold_width": 0.0, "border_alpha": 1.0, "border_color": stroke_color or "",
            "border_width": stroke_width if stroke_color else 0.0, "check_flag": 7,
            "content": json.dumps({"styles": [style], "text": text}, ensure_ascii=False),
            "fixed_height": -1.0, "fixed_width": -1.0, "font_category_id": "", "font_category_name": "",
            "font_id": "", "font_name": "", "font_path": font_path, "font_resource_id": "", "font_size": size,
            "font_source_platform": 0, "font_team_id": "", "font_title": "none", "font_url": "",
            "fonts": [], "force_apply_line_max_width": False, "global_alpha": 1.0, "group_id": "",
            "has_shadow": False, "id": _id(), "initial_scale": 1.0, "inner_padding": -1.0,
            "is_rich_text": False, "italic_degree": 0, "ktv_color": "", "language": "", "layer_weight": 1,
            "letter_spacing": 0.0, "line_feed": 1, "line_max_width": max_line_width, "line_spacing": 0.02,
            "multi_language_current": "none", "name": "", "original_size": [], "preset_category": "",
            "preset_category_id": "", "preset_has_set_alignment": False, "preset_id": "", "preset_index": 0,
            "preset_name": "", "recognize_task_id": "", "recognize_type": 0, "relevance_segment": [],
            "shadow_alpha": 0.9, "shadow_angle": -45.0, "shadow_color": "", "shadow_distance": 5.0,
            "shadow_point": {"x": 0.6363961030678928, "y": -0.6363961030678928}, "shadow_smoothing": 0.45,
            "shape_clip_x": False, "shape_clip_y": False, "source_from": "", "style_name": "",
            "sub_type": 0, "subtitle_keywords": None, "subtitle_template_original_fontsize": 0.0,
            "text_alpha": 1.0, "text_color": color, "text_curve": None, "text_preset_resource_id": "",
            "text_size": 30, "text_to_audio_ids": [], "tts_auto_update": False, "type": "text",
            "typesetting": 0, "underline": False, "underline_offset": 0.22, "underline_width": 0.05,
            "use_effect_default_color": True, "words": {"end_time": [], "start_time": [], "text": []},
        }
        self._mat("texts").append(material)
        anim = {"animations": [], "id": _id(), "multi_language_current": "none", "type": "sticker_animation"}
        self._mat("material_animations").append(anim)
        t = self.track("text", track)
        seg = self._segment(material["id"], start, duration, None, 1.0, 1.0, [anim["id"]],
                            self._clip(scale, x, y), render_index=14000 + track)
        t["segments"].append(seg)
        t["segments"].sort(key=lambda s: s["target_timerange"]["start"])
        self._recompute_duration()
        return seg

    def add_captions(self, captions: list, track: int = 0, **style) -> int:
        """captions: lista de objetos/dicts con start, end, text."""
        n = 0
        for c in captions:
            s, e, txt = (c["start"], c["end"], c["text"]) if isinstance(c, dict) else (c.start, c.end, c.text)
            if e > s and txt.strip():
                self.add_text(txt, s, e - s, track=track, **style)
                n += 1
        return n

    # ------------------------------------------------------------------ edición
    def remove_track(self, kind: str, index: int = 0) -> bool:
        same = [t for t in self.content["tracks"] if t["type"] == kind]
        if index < len(same):
            self.content["tracks"].remove(same[index])
            self._recompute_duration()
            return True
        return False

    def set_volume(self, kind: str, volume: float, track: int | None = None) -> int:
        n = 0
        tracks = [t for t in self.content["tracks"] if t["type"] == kind]
        for i, t in enumerate(tracks):
            if track is not None and i != track:
                continue
            for s in t["segments"]:
                s["volume"] = float(volume); n += 1
        return n

    def summary(self) -> dict:
        mats = self.content.get("materials", {})
        by_id = {m["id"]: m for k in ("videos", "audios", "texts") for m in mats.get(k, [])}
        tracks = []
        for t in self.content["tracks"]:
            segs = []
            for s in t["segments"]:
                m = by_id.get(s["material_id"], {})
                label = m.get("path") or ""
                if m.get("type") == "text":
                    try:
                        label = json.loads(m["content"])["text"]
                    except (KeyError, ValueError):
                        label = "?"
                tr = s["target_timerange"]
                segs.append({"start": tr["start"] / US, "duration": tr["duration"] / US,
                             "source_in": (s.get("source_timerange") or {}).get("start", 0) / US,
                             "speed": s.get("speed", 1.0), "volume": s.get("volume", 1.0),
                             "material": label})
            tracks.append({"type": t["type"], "segments": len(segs), "items": segs})
        return {"name": self.name, "canvas": f'{self.width}x{self.height}', "fps": self.content.get("fps"),
                "duration_s": round(self.duration, 3), "tracks": tracks}

    # ------------------------------------------------------------------ guardar
    def save(self, drafts_root: str | Path, overwrite: bool = False, backup_dir: str | Path | None = None) -> Path:
        drafts_root = Path(drafts_root)
        folder = drafts_root / self.name
        if folder.exists():
            if backup_dir:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                shutil.copytree(folder, Path(backup_dir) / f"{self.name}_{stamp}")
            if not overwrite:
                raise FileExistsError(f"Ya existe el borrador '{self.name}'. Usa overwrite=True.")
        folder.mkdir(parents=True, exist_ok=True)
        self.content["name"] = self.name
        self.content["update_time"] = int(time.time())
        self._recompute_duration()
        data = json.dumps(self.content, ensure_ascii=False)
        for fname in CONTENT_FILES:
            (folder / fname).write_text(data, encoding="utf-8")
        meta_path = folder / "draft_meta_info.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        now_us = int(time.time() * US)
        meta.update({
            "draft_fold_path": str(folder).replace("\\", "/"),
            "draft_id": meta.get("draft_id") or _id(),
            "draft_name": self.name,
            "draft_root_path": str(drafts_root).replace("\\", "/"),
            "tm_draft_create": meta.get("tm_draft_create") or now_us,
            "tm_draft_modified": now_us,
            "tm_duration": self.content["duration"],
            "draft_removable_storage_device": meta.get("draft_removable_storage_device", ""),
            "draft_cover": meta.get("draft_cover", ""),
            "draft_materials": self._meta_materials(),
        })
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return folder

    def _meta_materials(self) -> list[dict]:
        out = {0: [], 1: [], 2: [], 3: [], 6: [], 7: [], 8: []}
        now = int(time.time())
        for m in self.content["materials"].get("videos", []):
            out[0].append({"create_time": now, "duration": m["duration"], "extra_info": m["material_name"],
                           "file_Path": m["path"], "height": m["height"], "id": _id(), "import_time": now,
                           "import_time_ms": now * 1000, "item_source": 1, "md5": "",
                           "metetype": "photo" if m["type"] == "photo" else "video", "roughcut_time_range":
                           {"duration": m["duration"], "start": 0}, "sub_time_range": {"duration": -1, "start": -1},
                           "type": 0, "width": m["width"]})
        for m in self.content["materials"].get("audios", []):
            out[0].append({"create_time": now, "duration": m["duration"], "extra_info": m["name"],
                           "file_Path": m["path"], "height": 0, "id": _id(), "import_time": now,
                           "import_time_ms": now * 1000, "item_source": 1, "md5": "", "metetype": "music",
                           "roughcut_time_range": {"duration": m["duration"], "start": 0},
                           "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": 0})
        return [{"type": k, "value": v} for k, v in out.items()]

    def clone(self, name: str) -> "Draft":
        d = Draft(name, content=copy.deepcopy(self.content))
        d.content["id"] = _id()
        return d
