# Subtitle Maker

Makes English subtitles from the speech in a video, entirely on this PC, using
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI's Whisper
`large-v3` model) on your NVIDIA graphics card. Nothing is sent online.

A 20-minute video takes about a minute on an RTX 4070. The first run downloads the
speech model once (~3 GB).

## Use

Double-click **`Subtitle Maker.lnk`** (or run `uv run app.py`).

1. **Choose videos**, or drop them on the window (MP4, MKV, MOV, WebM… and audio files).
2. **Speech is in:** *English*, or *Another language* to translate it into English subtitles.
3. **Save as:** `.srt` (video players: VLC, TVs, Windows), `.vtt` (websites, Reelm), or both.

The subtitle files are saved next to each video with the same name (`movie.mp4` →
`movie.srt` / `movie.vtt`), so players pick them up automatically. When a video is
done: **Preview** shows the first lines, **Play** opens the video, the folder button
shows the file.

From a terminal:

```
uv run make_subs.py "D:\videos\movie.mp4"              # movie.srt
uv run make_subs.py movie.mp4 --vtt                    # also movie.vtt
uv run make_subs.py movie.mp4 --translate              # speech isn't English
uv run make_subs.py movie.mp4 --model medium           # faster, a bit less accurate
```

## Notes

- Lines are kept readable: at most 2 lines of 42 characters, at most 6 seconds each,
  split at pauses and sentence ends.
- Silence and music are skipped, which avoids made-up lines; still, proofread names
  and unusual words.
- Timings follow the video's own timeline, so the same `.vtt` stays in sync after
  encoding with Reelm Encoder (all qualities).
- Without an NVIDIA card it runs on the processor instead: it works, but much slower.

## Setup (once)

```
uv sync
```

`av` is pinned below 16 because newer versions break faster-whisper's audio reading.

The shortcut isn't portable (it holds paths on this PC). To make it again: a shortcut
to `.venv\Scripts\pythonw.exe` with the argument `app.py`, starting in this folder,
with the icon `assets\icon.ico`.

## Files

| File | What it is |
|---|---|
| `app.py` | the window (pywebview) and the work queue |
| `ui/index.html` | the window's page |
| `make_subs.py` | speech-to-subtitles logic, also usable from the terminal |
| `assets/` | app icon, and `make_icon.py` to redraw it (`uv run assets/make_icon.py`) |
| `settings.json` | your saved choices (created automatically) |
