# Testing guide

Use this when validating the tools on practice data, real sessions, or after code changes.

## Before any test

- [ ] `conda activate hmet-preprocess`
- [ ] Working on a **copy** of outputs paths, never writing into `raw/`
- [ ] `python scripts/check_env.py` passes
- [ ] You can play outputs in a normal video player (VLC, QuickTime, etc.)

## A. CLI smoke tests (no data required)

```bash
conda activate hmet-preprocess
python scripts/check_env.py
python convert_fps.py --help
python sync_av.py --help
```

Expected: all checks OK / help text prints; exit code 0.

## B. FPS conversion tests

### B1. Dry-run

```bash
python3 convert_fps.py -i SAMPLE.mp4 --fps 30 -o /tmp/hmet_fps_out --dry-run
```

Expected: prints planned ffmpeg command; no new media files.

### B2. Real convert + probe

```bash
python3 convert_fps.py -i SAMPLE.mp4 --fps 30 -o /tmp/hmet_fps_out --overwrite
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,avg_frame_rate \
  -of default=nw=1 /tmp/hmet_fps_out/SAMPLE_30fps.mp4
```

Expected: output exists; reported rate near 30 fps.

### B3. Batch / directory input

Point `-i` at a folder of videos; confirm all expected extensions are picked up.  
Add `--recursive` if files are nested.

### B4. Failure handling

Pass a missing path mixed with a good file. Expected: warning/skip or failure summary without crashing the interpreter; non-zero exit if any job failed.

## C. Sync / trim tests

### C1. Config validation

Start from `examples/sync_session.example.json`.  
Broken JSON or missing `reference.trim_*` should exit with a clear message.

### C2. Dry-run plan

```bash
python3 sync_av.py -c my_sync.json -o /tmp/hmet_sync_out --dry-run
```

Check:

- [ ] Reference start/duration look right  
- [ ] Each stream start = reference window shifted by sync offset  
- [ ] No unexpected huge negative starts (unless you intend `--allow-pad`)

### C3. Known-offset synthetic test (best accuracy check)

If you can create two short clips where the same flash/clap is at known frames (e.g. ref frame 30, other frame 90):

1. Set `align_to_ref_frame=30`, `sync_frame=90`, trim a short window after the event  
2. Run `sync_av.py`  
3. Confirm the flash occurs at the **same output time** in both `*_synced` files  

### C4. Real session QA checklist

After a real run:

- [ ] One output per configured stream + reference  
- [ ] All outputs have the **same duration** (within ~1 frame / small ffmpeg tolerance)  
- [ ] Sync event aligns between kid scene and parent scene  
- [ ] Sync event aligns between kid scene and at least one env cam  
- [ ] If env hardware sync is trusted: other env cams also align (or explain why not)  
- [ ] Trim window matches the intended interaction segment on kid scene  
- [ ] Audio (if kept) is not grossly out of sync on scene videos  

### C5. Video-only / missing optional streams

- Config with only `reference` and empty `streams` → trimmed kid scene only  
- Config without Reolink / without audio → should succeed  

## D. Regression checks after code changes

If you modify `convert_fps.py` or `sync_av.py`:

1. Re-run smoke tests (A)  
2. Re-run one FPS convert (B2)  
3. Re-run one sync dry-run + one short real sync (C2–C3)  
4. Note behavior changes in your PR / lab notes  

See [`modifying-the-code.md`](modifying-the-code.md).

## Common failures

| Symptom | Likely cause | What to try |
|---|---|---|
| `ffmpeg` / `ffprobe` not found | Not installed or not on `PATH` | Install; restart terminal; `which ffmpeg` |
| `Reference video not found` | Wrong path relative to config | Paths resolve relative to the **config file directory**, then cwd |
| `trim_end_frame exceeds reference duration` | Bad trim or wrong FPS | Check `ffprobe` duration; set `reference.fps` if probe is wrong |
| `starts before file begin` | Sync/trim math needs media before t=0 | Fix sync frames, shorten trim, or `--allow-pad` |
| `trim extends past EOF` | Stream too short for window | Fix sync/trim or `--allow-pad` |
| `output exists` | Prior run | Change `-o` or pass `--overwrite` |
| Sync looks “close but wrong” | Soft event / wrong frame | Remark using contact **onset**; nudge ±1–2 frames |
| Env cams disagree with each other | Hardware sync issue or bad inherit | Sync each env cam independently once and compare offsets |
| Neon eye “needs sync” confusion | Treating eye as separate recorder | Eye/gaze share Neon UTC with scene — no clap to scene |

## How to report a bug

Include:

1. Command line used  
2. Config JSON (paths can be redacted, keep numbers)  
3. Full terminal stdout/stderr  
4. `ffprobe -hide_banner` on the failing input  
5. OS + `ffmpeg -version` + `python3 --version`  

## Acceptance bar for “ready for analysis handoff”

A session preprocessing folder is ready when:

1. Sync JSON is filled and saved  
2. `sync_av.py` completed with all OK  
3. QA checklist (C4) signed off in `notes.txt`  
4. Raw data untouched  
