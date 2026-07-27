# Design: Batch Video Frame-Rate Conversion

> RA onboarding: start at the root [`README.md`](../README.md), then [`getting-started.md`](getting-started.md). This page is the design detail for `convert_fps.py`.

## Goal

Convert one or more input videos to a single target frame rate, producing new video files suitable for downstream HMET preprocessing. The tool must accept multiple paths (or a directory of videos) and apply the same FPS to every file in one run.

## Motivation

Mixed frame rates across recordings break temporal assumptions in pose estimation, tracking, and sequence models. Normalizing FPS early keeps clip length, sampling intervals, and train/eval pipelines consistent.

## Requirements

| Requirement | Detail |
|---|---|
| Multi-input | Accept one or more file paths and/or directories |
| Uniform target FPS | All outputs use the same `--fps` value |
| Non-destructive | Write to an output directory; never overwrite inputs by default |
| Predictable naming | Preserve stem; add a clear suffix (e.g. `_30fps`) |
| Robustness | Skip/report failures per file; continue batch |
| Dependency | Prefer system `ffmpeg`/`ffprobe` over heavy Python video stacks |

## Non-goals

- Changing resolution, aspect ratio, or color space (unless required by the encoder)
- Scene detection, trimming, or audio remixing beyond pass-through / drop
- GUI or web UI

## Approach

Use **ffmpeg** with the `fps` video filter to resample to the target rate, then re-encode video. Audio is copied when present (`-c:a copy`) so duration stays aligned without re-encoding audio.

```text
inputs ──► discover videos ──► for each file:
                                  ffprobe (optional metadata)
                                  ffmpeg -vf fps=<target> …
                               ──► output_dir/<stem>_<fps>fps.<ext>
```

### Why `fps` filter vs `-r`

- `-r` as an output option mainly sets the muxer/encoder rate and can drop/duplicate frames inconsistently depending on codec path.
- `-vf fps=N` explicitly resamples the frame stream to N frames per second, which is the intended behavior for “convert frame rate.”

### Encoding defaults

| Setting | Default | Rationale |
|---|---|---|
| Video codec | `libx264` | Widely compatible |
| Pixel format | `yuv420p` | Player / model-tool compatibility |
| CRF | `18` | High quality, still practical size |
| Preset | `medium` | Balance of speed vs size |
| Audio | copy | Avoid quality loss and extra time |
| Container | match input when possible; else `.mp4` | Predictable outputs |

All of the above are CLI-overridable.

## CLI interface

```bash
python convert_fps.py \
  --input path/to/a.mp4 path/to/dir/ more.mov \
  --fps 30 \
  --output-dir ./out_30fps \
  [--extensions .mp4 .mov .avi .mkv .webm] \
  [--overwrite] \
  [--dry-run] \
  [--workers 1] \
  [--crf 18] \
  [--preset medium] \
  [--video-codec libx264] \
  [--no-audio]
```

### Behavior notes

1. **Directory inputs** are expanded recursively or non-recursively (default: non-recursive; `--recursive` optional) for files matching `--extensions`.
2. **Duplicate stems** from different folders get a short parent-dir prefix or numeric suffix to avoid collisions in a flat output dir.
3. **Already-at-target FPS**: still re-encode unless `--skip-if-matching` is set (optional convenience).
4. **Exit code**: `0` if all succeeded; non-zero if any file failed (with a summary printed).

## Module layout

```text
hmet_play_preprocessing/
  docs/design_fps_conversion.md   # this document
  convert_fps.py                  # CLI + conversion logic
  requirements.txt                # minimal / empty (stdlib + ffmpeg)
```

Single-script layout keeps the first iteration easy to run and review. If the preprocessing suite grows, extract `discover_videos`, `probe_fps`, and `convert_one` into a small package later.

## Key functions

| Function | Responsibility |
|---|---|
| `discover_inputs(paths, extensions, recursive)` | Flatten files + dirs → unique video paths |
| `ensure_ffmpeg()` | Fail fast if `ffmpeg` / `ffprobe` missing |
| `probe_fps(path)` | Read average/nominal FPS via `ffprobe` |
| `build_ffmpeg_cmd(...)` | Construct argv for one conversion |
| `convert_one(...)` | Run conversion; return success/failure result |
| `main()` | argparse, batch orchestration, summary |

## Parallelism

Default `--workers 1` (sequential). Optional thread/process pool for I/O-bound batches. Cap workers by CPU count; each job is an ffmpeg subprocess.

## Error handling

- Missing ffmpeg → exit immediately with install hint.
- Unreadable / unsupported file → log error, continue.
- ffmpeg non-zero exit → capture stderr tail, mark failed.
- End with a table: path, source FPS (if known), target FPS, status.

## Testing plan

1. One short clip at 24 fps → 30 fps; verify `ffprobe` reports ~30.
2. Batch of mixed rates (24 / 30 / 60) → all report target FPS.
3. Directory input discovers expected files only.
4. `--dry-run` prints planned commands without writing.
5. Failure injection (bad path) leaves other outputs intact and yields non-zero exit.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Variable frame-rate (VFR) sources | Prefer `fps` filter; document that timing may stretch/compress slightly |
| Long re-encode time | Expose preset/CRF; optional workers |
| Audio sync after resample | Prefer stream copy; if issues arise, re-encode audio with `-c:a aac` |
| Disk space | Warn when output dir is on same volume as large inputs |

## Future extensions

- Passthrough if source FPS already equals target (`--skip-if-matching`)
- Hardware encoders (`h264_videotoolbox`, `h264_nvenc`)
- Manifest CSV of input → output → FPS for pipeline auditing
- Integration as a step in a larger HMET preprocessing pipeline config
