"""Transcripción (faster-whisper, opcional), SRT y detección de muletillas."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Caption:
    start: float
    end: float
    text: str


DEFAULT_FILLERS = {
    "es": ["eh", "ehh", "em", "emm", "mmm", "este", "o sea", "bueno", "pues", "vale", "digamos", "ah"],
    "en": ["um", "uh", "uhm", "erm", "like", "you know", "i mean", "so", "basically", "actually"],
}


def transcribe(path: str | Path, language: str | None = None, model: str = "small",
               device: str = "auto") -> tuple[list[Word], str]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper no está instalado. Ejecuta: pip install \"capcut-mcp[transcribe]\""
        ) from e
    compute = "int8"
    wm = WhisperModel(model, device=device, compute_type=compute)
    segments, info = wm.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True)
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(Word(round(w.start, 3), round(w.end, 3), w.word.strip()))
    return words, info.language


def save_words(words: list[Word], path: str | Path) -> Path:
    Path(path).write_text(json.dumps([asdict(w) for w in words], ensure_ascii=False, indent=1), encoding="utf-8")
    return Path(path)


def load_words(path: str | Path) -> list[Word]:
    return [Word(**w) for w in json.loads(Path(path).read_text(encoding="utf-8"))]


def group_captions(words: list[Word], max_words: int = 4, max_chars: int = 24, max_gap: float = 0.6,
                   uppercase: bool = False) -> list[Caption]:
    """Agrupa palabras en subtítulos cortos estilo reel."""
    caps: list[Caption] = []
    cur: list[Word] = []

    def flush():
        if cur:
            text = " ".join(w.text for w in cur).strip()
            caps.append(Caption(cur[0].start, cur[-1].end, text.upper() if uppercase else text))
            cur.clear()

    for w in words:
        if cur:
            joined = len(" ".join(x.text for x in cur)) + 1 + len(w.text)
            if (len(cur) >= max_words or joined > max_chars or w.start - cur[-1].end > max_gap
                    or re.search(r"[.!?]$", cur[-1].text)):
                flush()
        cur.append(w)
    flush()
    return caps


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(caps: list[Caption], path: str | Path) -> Path:
    lines = []
    for i, c in enumerate(caps, 1):
        lines += [str(i), f"{_ts(c.start)} --> {_ts(c.end)}", c.text, ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return Path(path)


def parse_srt(path: str | Path) -> list[Caption]:
    text = Path(path).read_text(encoding="utf-8-sig")
    out = []
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.*?)(?:\n\s*\n|\Z)", re.S)
    for m in pat.finditer(text):
        g = list(map(int, m.groups()[:8]))
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        out.append(Caption(s, e, m.group(9).strip()))
    return out


def find_fillers(words: list[Word], language: str = "es", extra: list[str] | None = None) -> list[tuple[float, float]]:
    """Rangos (s) de muletillas de una o varias palabras."""
    fillers = [f.lower() for f in DEFAULT_FILLERS.get(language[:2], []) + (extra or [])]
    norm = [re.sub(r"[^\wáéíóúñü' ]", "", w.text.lower()).strip() for w in words]
    ranges = []
    for i in range(len(words)):
        for f in fillers:
            parts = f.split()
            if norm[i:i + len(parts)] == parts:
                ranges.append((words[i].start, words[i + len(parts) - 1].end))
    return ranges


def remap_captions(caps: list[Caption], keeps: list[tuple[float, float]]) -> list[Caption]:
    """Reubica subtítulos del original en la línea de tiempo tras los cortes."""
    from .media import map_time
    out = []
    for c in caps:
        s, e = map_time(c.start, keeps), map_time(c.end, keeps)
        if s is None and e is None:
            continue
        if s is None:
            s = max(0.0, e - (c.end - c.start))
        if e is None:
            e = s + (c.end - c.start)
        if e > s:
            out.append(Caption(round(s, 3), round(e, 3), c.text))
    return out
