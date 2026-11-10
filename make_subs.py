"""Make English subtitles (.srt) for a video, entirely on this machine.

Usage:
    uv run make_subs.py "C:\\path\\to\\movie.mp4"
    uv run make_subs.py movie.mp4 --translate     # speech isn't English -> English subs
    uv run make_subs.py movie.mp4 --vtt           # also write a .vtt (for web players)
    uv run make_subs.py movie.mp4 --model medium  # faster, slightly less accurate

The .srt is saved next to the video with the same name.
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# The NVIDIA libraries come from pip packages; make their DLLs findable on Windows
# before faster-whisper / ctranslate2 is imported.
_site = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
for _sub in ("cublas", "cudnn", "cuda_nvrtc"):
    _bin = _site / _sub / "bin"
    if _bin.is_dir():
        os.add_dll_directory(str(_bin))
        os.environ["PATH"] = str(_bin) + os.pathsep + os.environ["PATH"]

from faster_whisper import WhisperModel  # noqa: E402

# Readable-subtitle limits (close to common streaming guidelines).
MAX_LINE_CHARS = 42
MAX_CUE_CHARS = MAX_LINE_CHARS * 2
MAX_CUE_SECONDS = 6.0
PAUSE_SPLIT_SECONDS = 0.8


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Cue:
    start: float
    end: float
    text: str


def load_model(name: str) -> tuple[WhisperModel, str]:
    try:
        return WhisperModel(name, device="cuda", compute_type="float16"), "GPU"
    except Exception as e:
        print(f"GPU not available ({e}); falling back to CPU, this will be slower.")
        return WhisperModel(name, device="cpu", compute_type="int8"), "CPU"


def group_into_cues(words: list[Word]) -> list[Cue]:
    """Turn a stream of timed words into short, readable subtitle cues."""
    cues: list[Cue] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            text = " ".join(w.text for w in current).strip()
            cues.append(Cue(current[0].start, current[-1].end, text))
            current.clear()

    for word in words:
        if current:
            text_len = len(" ".join(w.text for w in current)) + 1 + len(word.text)
            too_long = text_len > MAX_CUE_CHARS
            too_slow = word.end - current[0].start > MAX_CUE_SECONDS
            paused = word.start - current[-1].end > PAUSE_SPLIT_SECONDS
            if too_long or too_slow or paused:
                flush()
        current.append(word)
        # End the cue at a sentence end once it has a reasonable amount of text.
        last = word.text.rstrip()
        if last.endswith((".", "?", "!")) and len(" ".join(w.text for w in current)) > 20:
            flush()
    flush()

    # Keep each cue on screen long enough to read, without overlapping the next.
    for i, cue in enumerate(cues):
        min_end = cue.start + 1.0
        next_start = cues[i + 1].start if i + 1 < len(cues) else float("inf")
        cue.end = min(max(cue.end, min_end), next_start - 0.05)
    return cues


def wrap_two_lines(text: str) -> str:
    """Split a cue into at most two balanced lines."""
    if len(text) <= MAX_LINE_CHARS:
        return text
    words = text.split()
    best, best_diff = text, float("inf")
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) <= MAX_LINE_CHARS + 6 and len(b) <= MAX_LINE_CHARS + 6:
            diff = abs(len(a) - len(b))
            if diff < best_diff:
                best, best_diff = f"{a}\n{b}", diff
    return best


def timestamp(seconds: float, sep: str) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def write_srt(cues: list[Cue], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{timestamp(c.start, ',')} --> {timestamp(c.end, ',')}\n")
            f.write(f"{wrap_two_lines(c.text)}\n\n")


def write_vtt(cues: list[Cue], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for c in cues:
            f.write(f"{timestamp(c.start, '.')} --> {timestamp(c.end, '.')}\n")
            f.write(f"{wrap_two_lines(c.text)}\n\n")


class Stopped(Exception):
    """Raised when should_stop() asks transcribe() to give up."""


def transcribe(
    model: WhisperModel,
    video: Path,
    *,
    translate: bool = False,
    on_progress: Callable[[float, float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[Cue], float, str]:
    """Listen to a video and return (cues, duration_seconds, detected_language).

    on_progress(done_seconds, total_seconds) is called as speech is processed.
    """
    segments, info = model.transcribe(
        str(video),
        task="translate" if translate else "transcribe",
        language=None if translate else "en",
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,  # skip silence/music, which reduces made-up lines
        condition_on_previous_text=False,  # avoids repeating-text loops
    )
    total = info.duration or 0
    words: list[Word] = []
    for seg in segments:  # segments is lazy: the work happens in this loop
        if should_stop and should_stop():
            raise Stopped()
        for w in seg.words or []:
            if w.word.strip():
                words.append(Word(w.start, w.end, w.word.strip()))
        if on_progress:
            on_progress(seg.end, total)
    return group_into_cues(words), total, info.language


def main() -> int:
    parser = argparse.ArgumentParser(description="Make English subtitles for a video.")
    parser.add_argument("video", help="path to the video (or audio) file")
    parser.add_argument(
        "--model",
        default="large-v3",
        help="Whisper model: large-v3 (best, default), medium, small",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="speech is not English: translate it into English subtitles",
    )
    parser.add_argument("--vtt", action="store_true", help="also write a .vtt file")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        print(f"Can't find the video: {video}")
        return 1

    print(f"Loading the '{args.model}' model (first run downloads it, ~1.5 GB)...")
    model, device = load_model(args.model)
    print(f"Running on {device}. Listening to {video.name}...")

    started = time.time()

    def show(done: float, total: float) -> None:
        if total:
            pct = min(100, done / total * 100)
            print(f"\r  {pct:5.1f}%  ({timestamp(done, '.')[:8]} of {timestamp(total, '.')[:8]})", end="", flush=True)

    cues, _, _ = transcribe(model, video, translate=args.translate, on_progress=show)
    print()
    if not cues:
        print("No speech found in this video.")
        return 1

    srt_path = video.with_suffix(".srt")
    write_srt(cues, srt_path)
    print(f"Saved: {srt_path}")
    if args.vtt:
        vtt_path = video.with_suffix(".vtt")
        write_vtt(cues, vtt_path)
        print(f"Saved: {vtt_path}")

    print(f"{len(cues)} subtitles in {time.time() - started:.0f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
