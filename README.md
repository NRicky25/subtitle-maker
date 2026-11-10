# Subtitle Maker

Makes English subtitles from the speech in a video, entirely on your PC, using
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI's Whisper
`large-v3` model) on an NVIDIA graphics card. Nothing is sent online.

A 20-minute video takes about a minute on an RTX 4070.

## Requirements

- **Windows 10 or 11** (64-bit)
- **[uv](https://docs.astral.sh/uv/)**: installs Python 3.12 and all packages for you.
  Install it once with `winget install --id=astral-sh.uv -e`, then open a new terminal.
- **An NVIDIA graphics card** with an up-to-date driver (CUDA 12 support) for full speed.
  Without one it still works, on the processor, but much slower.
- **About 6 GB of free disk space**: ~1.5 GB of packages, plus the ~3 GB speech model
  downloaded the first time you make subtitles.

You don't need to install Python, CUDA or ffmpeg yourself: they come with the packages.

## Install

```
git clone https://github.com/NRicky25/subtitle-maker.git
cd subtitle-maker
.\setup.cmd
```

(Or download the ZIP from GitHub, extract it, and double-click **`setup.cmd`**.)

`setup.cmd` checks for uv, installs everything (`uv sync`) and creates a
**Subtitle Maker** shortcut in the folder. Run it again after updating
(`git pull`) to pick up new packages.

## Use

Double-click the **Subtitle Maker** shortcut (or run `uv run app.py`).

1. **Choose videos**, or drop them on the window (MP4, MKV, MOV, WebM… and audio files).
2. **Speech is in:** *English*, or *Another language* to translate it into English subtitles.
3. **Save as:** `.srt` (video players: VLC, TVs, Windows), `.vtt` (websites, Reelm), or both.

The subtitle files are saved next to each video with the same name (`movie.mp4` →
`movie.srt` / `movie.vtt`), so players pick them up automatically. When a video is
done: **Preview** shows the first lines, **Play** opens the video, the folder button
shows the file.

The first video takes a little longer while the speech model downloads and loads;
the top-right badge turns from "Loading speech model…" into "Ready".

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

## Troubleshooting

| Problem | Fix |
|---|---|
| `'uv' is not recognized` | Install uv (see Requirements), then open a **new** terminal. |
| Badge says "CPU (slower)" on a PC with an NVIDIA card | Update the NVIDIA driver, then restart the app. |
| "The graphics card ran out of memory" | Close games/other GPU apps, or use `--model medium`. |
| The window is blank | Install the [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (built into Windows 11). |

## Files

| File | What it is |
|---|---|
| `setup.cmd` | one-click install + shortcut |
| `app.py` | the window (pywebview) and the work queue |
| `ui/index.html` | the window's page |
| `make_subs.py` | speech-to-subtitles logic, also usable from a terminal |
| `assets/` | app icon, and `make_icon.py` to redraw it (`uv run assets/make_icon.py`) |
| `settings.json` | your saved choices (created automatically, not in git) |

`av` is pinned below 16 because newer versions break faster-whisper's audio reading.
