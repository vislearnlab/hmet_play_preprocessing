# HMET Preprocessing

Tools and design docs for preparing multi-camera HMET session recordings before analysis.

This repo is meant to be **run and extended by RAs**: normalize video frame rates, then sync/trim all streams to the kid Neon scene-camera timeline.

## What we process

| Source | Cameras / data |
|---|---|
| Kid + parent | Pupil Labs **Neon** scene (+ eye/gaze timeseries) |
| Environment | 3× Orbbec depth/color cams (top-down, adult side, toddler side) |
| Optional | Reolink context cam, external audio |

Hardware capture notes live in [`recording-setup-spec.md`](recording-setup-spec.md).  
Software sync/trim design lives in [`docs/design_av_sync.md`](docs/design_av_sync.md).

## Quick start

### 1. Prerequisites

- macOS, Linux, or Windows
- **Python 3.9+** (stdlib only for current scripts)
- **ffmpeg** and **ffprobe** on your `PATH`

```bash
# macOS
brew install ffmpeg

# check
ffmpeg -version
ffprobe -version
python3 --version
```

No `pip install` is required for the current scripts (see `requirements.txt`).

### 2. Clone / open the repo

```bash
cd hmet_play_preprocessing
```

### 3. Smoke-test the CLIs

```bash
python3 convert_fps.py --help
python3 sync_av.py --help
```

### 4. Typical session workflow

```text
raw session media
    → (optional) convert_fps.py     # common video FPS if needed
    → fill sync JSON from example
    → sync_av.py --dry-run
    → sync_av.py                    # write trimmed/aligned videos
    → QA spot-check
    → (later) Neon CSV windowing    # gaze/fixations — not automated yet
```

Details: [`docs/getting-started.md`](docs/getting-started.md) and [`docs/pipeline-overview.md`](docs/pipeline-overview.md).

## Tools

| Script | Purpose |
|---|---|
| `convert_fps.py` | Batch-convert videos to one target FPS |
| `sync_av.py` | Trim kid scene gold standard; sync/trim other videos/audio to the same window |

### Frame-rate conversion example

```bash
python3 convert_fps.py \
  --input /path/to/videos_or_files \
  --fps 30 \
  --output-dir /path/to/out_30fps \
  --dry-run
```

### Sync / trim example

1. Copy [`examples/sync_session.example.json`](examples/sync_session.example.json).
2. Point paths at your session files; set trim + sync frames.
3. Run:

```bash
python3 sync_av.py \
  --config /path/to/session_sync.json \
  --output-dir /path/to/session_synced \
  --dry-run
```

Remove `--dry-run` when the printed plan looks right.

## Documentation map (start here if you are an RA)

| Doc | Read when… |
|---|---|
| [`docs/getting-started.md`](docs/getting-started.md) | First day setup + first real run |
| [`docs/pipeline-overview.md`](docs/pipeline-overview.md) | You need the big picture / processing order |
| [`docs/testing-guide.md`](docs/testing-guide.md) | You are validating outputs or filing bugs |
| [`docs/modifying-the-code.md`](docs/modifying-the-code.md) | You need to change scripts or configs |
| [`docs/design_fps_conversion.md`](docs/design_fps_conversion.md) | FPS tool design details |
| [`docs/design_av_sync.md`](docs/design_av_sync.md) | Sync/trim design, Neon notes, finding sync points |
| [`examples/README.md`](examples/README.md) | How to use example configs |
| [`recording-setup-spec.md`](recording-setup-spec.md) | Env camera hardware / capture draft |

## Important conventions

- **Gold timeline:** kid Neon **scene** video.
- **Trim once** on the kid scene (`trim_start_frame` … `trim_end_frame`, end exclusive).
- **One sync point per external stream** (parent scene, each env cam, …).  
  Do **not** clap-sync kid eye ↔ kid scene (same Neon recording / UTC clock).
- Prefer `--dry-run` before writing large outputs.
- Never overwrite raw captures; scripts write to an output directory.

## Repo layout

```text
hmet_play_preprocessing/
├── README.md
├── requirements.txt
├── convert_fps.py
├── sync_av.py
├── recording-setup-spec.md
├── docs/
│   ├── getting-started.md
│   ├── pipeline-overview.md
│   ├── testing-guide.md
│   ├── modifying-the-code.md
│   ├── design_fps_conversion.md
│   └── design_av_sync.md
└── examples/
    ├── README.md
    └── sync_session.example.json
```

## Status / known gaps

Working now:

- Batch FPS conversion via ffmpeg
- Config-driven sync/trim for video (and optional audio files)

Not built yet (see design docs “Future extensions”):

- Neon `gaze.csv` / fixation windowing from `world_timestamps.csv`
- Dual-pane offset scrubber UI
- Automatic audio/motion sync helpers

## Who to ask

If something in the designs conflicts with lab SOP (especially Reolink sync policy or Orbbec export paths), check with the project lead before changing conventions.
