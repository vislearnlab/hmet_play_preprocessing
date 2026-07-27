# Modifying the code

Guidance for RAs and collaborators who need to change scripts or conventions.

## Principles

1. **Prefer config and flags over hard-coding** session-specific paths or frame numbers.  
2. **Keep kid Neon scene as the software gold standard** unless the project lead changes SOP.  
3. **Do not break dry-run behavior** — every destructive path should be previewable.  
4. **Match existing style**: stdlib + ffmpeg subprocesses, clear CLI errors, per-file results.  
5. Update **design docs + examples** when behavior or config shape changes.

## Where things live

| Concern | File |
|---|---|
| FPS batch conversion | `convert_fps.py` |
| Sync/trim | `sync_av.py` |
| Conda env (RA default) | `environment.yml`, `setup.sh`, `scripts/check_env.py` |
| FPS design | `docs/design_fps_conversion.md` |
| Sync design / Neon / sync-point finding | `docs/design_av_sync.md` |
| Example session config | `examples/sync_session.example.json` |
| Env hardware draft | `recording-setup-spec.md` |

## Safe change workflow

1. Branch or copy files if your lab uses git; otherwise snapshot the script before editing.  
2. Read the relevant design doc section.  
3. Make the smallest change that solves the need.  
4. Run [`testing-guide.md`](testing-guide.md) sections A–C that apply.  
5. Update docs/examples if flags or JSON fields changed.  
6. Note the change in session or lab changelog.

## Extending the sync config

`sync_av.py` currently reads:

- `reference.path`, `trim_start_frame`, `trim_end_frame`, optional `fps`  
- `streams[]`: `name`, `path`, `align_to_ref_frame`, and exactly one of `sync_frame` / `sync_sec` / `sync_sample`  
- optional `type`: `video` \| `audio`

The example file may include a nested `neon` block (`recording_dir`, `world_timestamps`, `info`).  
**That block is reserved for future CSV windowing** and is ignored by `sync_av.py` today — safe to keep for documentation.

If you add a new JSON field:

1. Document it in `design_av_sync.md`  
2. Validate it in `load_config()` with a clear error  
3. Extend `examples/sync_session.example.json`  
4. Mention it in `examples/README.md`

## Common extension ideas (priority suggestions)

| Idea | Notes |
|---|---|
| Neon CSV windowing | Use kid `world_timestamps.csv` rows for trim frames → UTC `[t0, t1)`; filter `gaze.csv` etc. |
| Offset scrubber | Small UI/CLI to nudge sync by ±1 frame and print JSON fields |
| Audio cross-correlation | Propose `sync_sec` between two files with audio |
| Env offset inherit | Flag: copy offset from `env_topdown` to other env cams |
| Hardware encoder | e.g. `h264_videotoolbox` / `h264_nvenc` via `--video-codec` (already overridable) |

## Coding tips for these scripts

- Use `ffprobe` JSON for FPS/duration; do not assume constant FPS without checking.  
- Prefer re-encode for accurate video trims (already the default).  
- Keep exit code non-zero if any item in a batch failed.  
- Resolve relative media paths against the **config file’s directory** first (already implemented in `sync_av.py`).

## What not to change casually

- Inclusive start / **exclusive end** frame convention for trim  
- Output naming (`*_synced`, `*_30fps`) without updating docs  
- Treating env top-down as software gold instead of kid scene  
- Adding heavy dependencies without discussion (keep scripts easy to run on lab machines)

## Questions for the project lead before changing SOP

- Is Reolink a synced channel or loose backup?  
- Required common FPS for downstream models?  
- Should Neon audio be enabled at capture by default?  
- Exact Orbbec export paths / naming from the Windows capture PC?
