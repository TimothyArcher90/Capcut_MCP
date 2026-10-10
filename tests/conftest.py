import shutil
import subprocess
from pathlib import Path

import pytest

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado")


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPCUT_STUDIO_ROOT", str(tmp_path / "studio"))
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    monkeypatch.setenv("CAPCUT_DRAFTS_DIR", str(drafts))
    return tmp_path


@pytest.fixture
def talking_clip(tmp_path) -> Path:
    """Clip 16:9 de 6 s: tono 1 s, silencio 1.5 s, tono 1.5 s, silencio 1 s, tono 1 s."""
    out = tmp_path / "talk.mp4"
    tone = "sine=frequency=440:sample_rate=48000"
    graph = (
        f"{tone}:duration=1[a1];anullsrc=r=48000:cl=mono,atrim=duration=1.5[s1];"
        f"{tone}:duration=1.5[a2];anullsrc=r=48000:cl=mono,atrim=duration=1[s2];"
        f"{tone}:duration=1[a3];[a1][s1][a2][s2][a3]concat=n=5:v=0:a=1[a]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=size=640x360:rate=30:duration=6", "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
        check=True,
    )
    return out


@pytest.fixture
def music_clip(tmp_path) -> Path:
    out = tmp_path / "music.mp3"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=220:duration=2", str(out)], check=True)
    return out
