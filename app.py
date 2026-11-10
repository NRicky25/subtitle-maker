"""Subtitle Maker window.

Run:  uv run app.py      (or double-click "Subtitle Maker.lnk")

The window is HTML/CSS (ui/index.html) shown by pywebview. This file loads the
Whisper model once, works through the queue of videos one at a time, and pushes
progress to the page.
"""

import base64
import ctypes
import io
import itertools
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import make_subs  # sets up the NVIDIA DLLs before faster-whisper loads  # noqa: I001
import av
import darkdetect
import webview

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "settings.json"
ICON_FILE = HERE / "assets" / "icon.ico"
TITLE = "Subtitle Maker"
APP_ID = "local.subtitlemaker"
MODEL = "large-v3"
MEDIA_EXT = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".ts", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".3gp", ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus",
}
PREVIEW_CUES = 8

window: webview.Window | None = None  # kept out of Api so pywebview doesn't expose it


# ---------------- settings ----------------
def load_settings() -> dict[str, Any]:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("language") not in ("en", "other"):
        data["language"] = "en"
    if data.get("format") not in ("srt", "vtt", "both"):
        data["format"] = "both"
    data.setdefault("last_dir", str(Path.home() / "Videos"))
    return data


def save_settings(data: dict[str, Any]) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------- helpers ----------------
def emit(**event: Any) -> None:
    if window is not None:
        try:
            window.evaluate_js(f"window.onEvent({json.dumps(event)})")
        except Exception:
            pass  # window is closing


def fmt_clock(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def fmt_took(seconds: float) -> str:
    return f"{seconds:.0f}s" if seconds < 90 else f"{seconds / 60:.1f} min"


def thumbnail(path: Path) -> tuple[str, float]:
    """(JPEG data URL of a frame ~10% in, duration in seconds); ('', 0) if unknown."""
    try:
        with av.open(str(path)) as c:
            duration = (c.duration or 0) / av.time_base
            if not c.streams.video:
                return "", duration
            stream = c.streams.video[0]
            if duration > 4:
                c.seek(int(duration * 0.1 / stream.time_base), stream=stream)
            for frame in c.decode(stream):
                img = frame.to_image()
                img.thumbnail((320, 180))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=80)
                return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), duration
    except Exception:
        pass
    return "", 0.0


def gpu_name() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip().splitlines()[0].replace("NVIDIA ", "").replace("GeForce ", "")
    except Exception:
        return ""


def friendly_error(e: Exception) -> str:
    msg = str(e).strip() or e.__class__.__name__
    low = msg.lower()
    if "no audio" in low or "does not contain any stream" in low or "audio stream" in low:
        return "This file has no sound track."
    if "out of memory" in low:
        return "The graphics card ran out of memory. Close other GPU apps and retry."
    if "invalid data" in low:
        return "This file couldn't be read. It may be damaged or not a video."
    return msg[:220] + ("…" if len(msg) > 220 else "")


# ---------------- worker ----------------
@dataclass
class Job:
    id: int
    path: Path
    translate: bool
    formats: tuple[str, ...]


class Worker:
    def __init__(self) -> None:
        self.jobs: queue.Queue[Job] = queue.Queue()
        self.cancelled: set[int] = set()
        self.ids = itertools.count(1)
        self.model = None
        self.device = ""
        threading.Thread(target=self._loop, daemon=True).start()

    def add(self, path: Path, translate: bool, formats: tuple[str, ...]) -> int:
        job = Job(next(self.ids), path, translate, formats)
        self.jobs.put(job)
        return job.id

    def _load_model(self) -> None:
        emit(engine="loading", text="Loading speech model…")
        self.model, self.device = make_subs.load_model(MODEL)
        if self.device == "GPU":
            name = gpu_name()
            emit(engine="ready", text=f"Ready · {name}" if name else "Ready · graphics card")
        else:
            emit(engine="ready", text="Ready · CPU (slower)")

    def _loop(self) -> None:
        try:
            self._load_model()  # start warming up right away
        except Exception as e:
            emit(engine="idle", text="Model failed to load")
            print("model load failed:", e)
        while True:
            job = self.jobs.get()
            if job.id in self.cancelled:
                emit(id=job.id, state="cancelled", status="Cancelled")
                continue
            try:
                if self.model is None:
                    emit(id=job.id, state="loading", status="Loading speech model…")
                    self._load_model()
                self._run(job)
            except make_subs.Stopped:
                emit(id=job.id, state="cancelled", status="Cancelled", percent=0)
            except Exception as e:
                emit(id=job.id, state="error", status=friendly_error(e))

    def _run(self, job: Job) -> None:
        thumb, duration = thumbnail(job.path)
        emit(
            id=job.id,
            state="loading",
            thumbnail=thumb,
            duration=fmt_clock(duration) if duration else "",
            status="Listening…",
        )
        started = time.monotonic()
        last = [0.0]

        def progress(done: float, total: float) -> None:
            now = time.monotonic()
            if now - last[0] < 0.25 or not total:
                return
            last[0] = now
            pct = min(99.5, done / total * 100)
            elapsed = now - started
            left = elapsed / max(done, 1) * (total - done) if done > 5 else None
            parts = [f"{pct:.0f}%", f"{fmt_clock(done)} of {fmt_clock(total)}"]
            if left is not None:
                parts.append(f"about {fmt_took(left)} left")
            emit(id=job.id, state="working", percent=pct, status="  ·  ".join(parts))

        cues, _, _ = make_subs.transcribe(
            self.model,
            job.path,
            translate=job.translate,
            on_progress=progress,
            should_stop=lambda: job.id in self.cancelled,
        )
        if not cues:
            raise RuntimeError("No speech found in this video.")

        written: list[Path] = []
        if "srt" in job.formats:
            written.append(job.path.with_suffix(".srt"))
            make_subs.write_srt(cues, written[-1])
        if "vtt" in job.formats:
            written.append(job.path.with_suffix(".vtt"))
            make_subs.write_vtt(cues, written[-1])

        took = time.monotonic() - started
        kinds = " + ".join(p.suffix for p in written)
        emit(
            id=job.id,
            state="done",
            percent=100,
            sub=str(written[0]),
            cues=[{"start": c.start, "text": make_subs.wrap_two_lines(c.text)} for c in cues[:PREVIEW_CUES]],
            cueCount=len(cues),
            status=f"{len(cues)} subtitles  ·  {kinds}  ·  took {fmt_took(took)}",
        )


# ---------------- API the page can call ----------------
class Api:
    def __init__(self) -> None:
        self._settings = load_settings()
        self._worker = Worker()

    def init(self) -> dict[str, Any]:
        return {"language": self._settings["language"], "format": self._settings["format"]}

    def set_option(self, key: str, value: str) -> None:
        if key in ("language", "format"):
            self._settings[key] = value
            save_settings(self._settings)

    def choose_files(self) -> list[str]:
        assert window is not None
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if dialog is None:
            dialog = webview.OPEN_DIALOG
        start = self._settings["last_dir"]
        exts = ";".join(f"*{e}" for e in sorted(MEDIA_EXT))
        picked = window.create_file_dialog(
            dialog,
            directory=start if Path(start).is_dir() else str(Path.home()),
            allow_multiple=True,
            file_types=(f"Videos and audio ({exts})", "All files (*.*)"),
        )
        if not picked:
            return []
        paths = [str(p) for p in picked]
        self._settings["last_dir"] = str(Path(paths[0]).parent)
        save_settings(self._settings)
        return paths

    def add(self, paths: list[str]) -> dict[str, Any]:
        translate = self._settings["language"] == "other"
        fmt = self._settings["format"]
        formats = ("srt", "vtt") if fmt == "both" else (fmt,)
        jobs, skipped = [], []
        for raw in paths:
            p = Path(raw)
            if not p.is_file() or p.suffix.lower() not in MEDIA_EXT:
                skipped.append(raw)
                continue
            job_id = self._worker.add(p, translate, formats)
            jobs.append({"id": job_id, "path": str(p), "name": p.name, "folder": str(p.parent)})
        return {"jobs": jobs, "skipped": skipped}

    def cancel(self, job_id: int) -> None:
        self._worker.cancelled.add(int(job_id))

    def open_path(self, path: str) -> None:
        if path and Path(path).exists():
            os.startfile(path)

    def reveal(self, path: str) -> None:
        if path and Path(path).exists():
            subprocess.Popen(["explorer", f"/select,{path}"])


# ---------------- native window touches (Windows) ----------------
def style_native_window() -> None:
    user32 = ctypes.windll.user32
    try:
        hwnd = int(window.native.Handle.ToInt64())  # type: ignore[union-attr]
    except Exception:
        hwnd = user32.FindWindowW(None, TITLE)
    if not hwnd:
        return
    if ICON_FILE.exists():
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        for which, metric in ((1, 11), (0, 49)):
            px = user32.GetSystemMetrics(metric)
            icon = user32.LoadImageW(None, str(ICON_FILE), 1, px, px, 0x10)
            if icon:
                user32.SendMessageW(hwnd, 0x80, which, icon)
    dark = (darkdetect.theme() or "Light") == "Dark"
    dwm = ctypes.windll.dwmapi
    value = ctypes.c_int(1 if dark else 0)
    dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
    caption = ctypes.c_int(0x00150F0D if dark else 0x00F9F6F5)  # page background as 0x00BBGGRR
    dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)


def hook_file_drop() -> None:
    """Files dropped on the window arrive here with their full paths."""
    try:
        from webview.dom import DOMEventHandler
    except ImportError:
        return

    def on_drop(e: dict[str, Any]) -> None:
        files = (e.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths and window is not None:
            window.evaluate_js(f"window.addDropped({json.dumps(paths)})")

    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)  # type: ignore[union-attr]


def main(on_ready: Any = None) -> None:
    global window
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass
    dark = (darkdetect.theme() or "Light") == "Dark"
    window = webview.create_window(
        TITLE,
        url=str(HERE / "ui" / "index.html"),
        js_api=Api(),
        width=1000,
        height=780,
        min_size=(720, 600),
        background_color="#0D0F15" if dark else "#F5F6F9",
    )
    window.events.shown += lambda *_: style_native_window()
    window.events.loaded += lambda *_: hook_file_drop()
    webview.start(on_ready, window) if on_ready else webview.start()


if __name__ == "__main__":
    main()
