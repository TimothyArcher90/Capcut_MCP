import json
from pathlib import Path

from conftest import needs_ffmpeg

from capcut_mcp import media
from capcut_mcp import transcribe as tr
from capcut_mcp.autoedit import AutoEditOptions, auto_edit, fill_scale
from capcut_mcp.draft import Draft, doctor, list_drafts
from capcut_mcp.workspace import PROJECT_DIRS, Project


def test_project_structure(studio):
    p = Project.create("Mi Reel Ñandú")
    assert p.path.name.endswith("_mi-reel-nandu")
    for d in PROJECT_DIRS:
        assert (p.path / d).is_dir()
    assert Project.resolve("mi reel ñandú").path == p.path
    assert (studio / "studio" / "_Library" / "music").is_dir()


def test_ranges_math():
    keeps = media.keep_ranges_from_silences(10, [(2, 4), (7, 8)], padding=0.1)
    assert keeps == [(0.0, 2.1), (3.9, 7.1), (7.9, 10.0)]
    assert media.subtract_ranges([(0, 10)], [(2, 3)]) == [(0, 2), (3, 10)]
    assert media.map_time(4.0, keeps) == 2.1 + 0.1
    assert media.map_time(3.0, keeps) is None


def test_captions_and_srt(tmp_path):
    words = [tr.Word(0.0, 0.3, "Hola"), tr.Word(0.3, 0.6, "eh"), tr.Word(0.6, 1.0, "mundo."),
             tr.Word(2.0, 2.4, "Otra"), tr.Word(2.4, 2.8, "frase")]
    caps = tr.group_captions(words, max_words=4)
    assert [c.text for c in caps] == ["Hola eh mundo.", "Otra frase"]
    srt = tr.write_srt(caps, tmp_path / "x.srt")
    back = tr.parse_srt(srt)
    assert back[1].start == 2.0 and back[1].text == "Otra frase"
    assert tr.find_fillers(words, "es") == [(0.3, 0.6)]


def test_fill_scale():
    assert fill_scale(1920, 1080, 1080, 1920, "fill") == round((16 / 9) / (9 / 16), 4)
    assert fill_scale(1920, 1080, 1080, 1920, "fit") == 1.0


@needs_ffmpeg
def test_draft_roundtrip(studio, talking_clip, music_clip, tmp_path):
    d = Draft.new("prueba", "9:16")
    d.add_jump_cuts(talking_clip, [(0, 1.1), (2.4, 4.1)], scale=3.16)
    d.add_text("HOOK", 0, 2, size=12, y=0.55)
    d.add_audio(music_clip, start=0, volume=0.2, loop_to=d.duration, fade_out=0.5)
    folder = d.save(tmp_path / "drafts")
    content = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    assert (folder / "draft_info.json").exists() and (folder / "draft_meta_info.json").exists()
    assert content["canvas_config"] == {"height": 1920, "ratio": "original", "width": 1080}
    assert content["duration"] == 2_800_000
    video = [t for t in content["tracks"] if t["type"] == "video"][0]
    assert [s["source_timerange"]["start"] for s in video["segments"]] == [0, 2_400_000]
    assert video["segments"][1]["target_timerange"]["start"] == 1_100_000
    audio = [t for t in content["tracks"] if t["type"] == "audio"][0]
    assert len(audio["segments"]) == 2  # música de 2 s en bucle hasta 2.8 s
    ids = {m["id"] for k in content["materials"].values() if isinstance(k, list) for m in k}
    for t in content["tracks"]:
        for s in t["segments"]:
            assert s["material_id"] in ids
            assert all(r in ids for r in s["extra_material_refs"])
    loaded = Draft.load(folder)
    summ = loaded.summary()
    assert summ["duration_s"] == 2.8
    assert any(i["material"] == "HOOK" for t in summ["tracks"] for i in t["items"])
    assert list_drafts(tmp_path / "drafts")[0]["readable_json"] is True
    assert doctor(tmp_path / "drafts")["status"] == "ok"


@needs_ffmpeg
def test_media_pipeline(studio, talking_clip, music_clip):
    p = Project.create("media")
    sil = media.detect_silences(talking_clip, -40, 0.4)
    assert len(sil) == 2
    keeps = media.keep_ranges_from_silences(6.0, sil, 0.1)
    out = media.render_ranges(talking_clip, keeps, p.dir("cuts") / "jc.mp4")
    from capcut_mcp.ffmpeg import probe
    assert abs(probe(out)["duration"] - sum(e - s for s, e in keeps)) < 0.25
    enh = media.enhance_audio(talking_clip, p.dir("processed_audio") / "e.mp4", "voice")
    assert probe(enh)["has_audio"]
    rf = media.reframe(out, p.dir("reframed") / "r.mp4", "9:16", "blur")
    assert (probe(rf)["width"], probe(rf)["height"]) == (1080, 1920)
    mixed = media.mix_music(rf, music_clip, p.dir("exports") / "m.mp4")
    assert probe(mixed)["has_audio"]
    caps = [tr.Caption(0, 1, "Hola"), tr.Caption(1, 2, "mundo")]
    srt = tr.write_srt(caps, p.dir("subtitles") / "s.srt")
    burned = media.burn_subtitles(mixed, srt, p.dir("exports") / "b.mp4")
    assert burned.exists()


@needs_ffmpeg
def test_auto_edit(studio, talking_clip, music_clip):
    p = Project.create("auto")
    opts = AutoEditOptions(silence_db=-40, min_silence=0.4, transcribe=False, music=str(music_clip),
                           hook_text="MIRA ESTO", render=True)
    rep = auto_edit(p, talking_clip, opts, Path(studio / "drafts"))
    assert rep["duration_after"] < rep["duration_before"]
    assert Path(rep["draft_path"], "draft_content.json").exists()
    assert Path(rep["render"]).exists()
    assert p.manifest["drafts"][0]["name"] == rep["draft_path"].split("/")[-1].split("\\")[-1]


@needs_ffmpeg
def test_root_meta_registration(tmp_path, talking_clip):
    root = tmp_path / "drafts"
    root.mkdir()
    existing = {"draft_fold_path": str(root / "1012 (1)"), "draft_id": "X", "draft_name": "1012 (1)",
                "draft_json_file": "", "tm_draft_modified": 1, "tm_duration": 0, "draft_cover": "",
                "draft_type": "", "draft_timeline_materials_size_": 0}
    (root / "root_meta_info.json").write_text(json.dumps({"all_draft_store": [existing], "draft_ids": 1,
                                                          "root_path": str(root)}))
    d = Draft.new("test_mcp")
    d.add_video(talking_clip)
    d.save(root)
    assert d.index_status == "registrado"
    idx = json.loads((root / "root_meta_info.json").read_text())
    assert [e["draft_name"] for e in idx["all_draft_store"]] == ["test_mcp", "1012 (1)"]
    assert idx["draft_ids"] == 2 and "draft_type" in idx["all_draft_store"][0]
    d.save(root, overwrite=True)  # no duplica
    assert len(json.loads((root / "root_meta_info.json").read_text())["all_draft_store"]) == 2
