# Pipeline overview

End-to-end view of how a session moves from capture folders to analysis-ready media.

## Stream inventory

```text
                    [env_topdown]          Orbbec (hardware-synced trio)
                         |
                         v
   [env_adult_side] → Adult   Toddler ← [env_toddler_side]
                         ↑         ↑
                   parent Neon   kid Neon
                   scene (+eye)  scene (+eye)   ← kid scene = software GOLD
```

| ID (suggested) | Source | Sync to kid scene? |
|---|---|---|
| `kid_scene` | Neon Cloud/native scene mp4 | **Reference** (defines trim) |
| kid eye / gaze CSV | Same Neon recording | No clap — same UTC clock |
| `parent_scene` | Parent Neon scene mp4 | Yes |
| parent eye / gaze CSV | Same parent Neon recording | Via parent scene / UTC |
| `env_topdown` | Orbbec cam 1 | Yes |
| `env_adult_side` | Orbbec cam 2 | Yes (or inherit from top-down) |
| `env_toddler_side` | Orbbec cam 3 | Yes (or inherit from top-down) |
| `reolink` | Optional | Only if lab decides it is synced |

Capture hardware draft: [`../recording-setup-spec.md`](../recording-setup-spec.md).  
Neon on-disk format: [Pupil Labs docs](https://docs.pupil-labs.com/neon/data-collection/data-format/).

## Processing order

```text
1. Organize raw inputs
      Neon kid folder, Neon parent folder, env mkv/mp4s, optional Reolink/audio

2. (Optional) FPS normalize — convert_fps.py
      Use when you need a common video rate for indexing / models.
      Neon scene is natively ~30 Hz; env draft is ~15 Hz; eye is ~200 Hz.
      Prefer converting time via seconds/UTC for Neon CSVs rather than
      forcing eye video to 30 Hz unless a tool requires it.

3. Choose analysis window on kid scene
      trim_start_frame, trim_end_frame (end exclusive)

4. Mark sync points
      For each external video: (align_to_ref_frame on kid, sync_frame on that file)
      Same clap/flash frame on kid for all streams when possible

5. Dry-run sync — sync_av.py --dry-run

6. Write synced/trimmed videos — sync_av.py

7. QA (see testing-guide.md)

8. (Future) Window Neon gaze/fixation/IMU CSVs
      Using world_timestamps.csv UTC range for the trim window
      Not implemented as a script yet
```

## What “synced” means here

All successful outputs cover the **same duration** on the session clock.  
Frame 0 of every `*_synced` file corresponds to kid scene `trim_start_frame`.

Math (seconds):

```text
ref_start = trim_start_frame / kid_fps
ref_end   = trim_end_frame   / kid_fps
duration  = ref_end - ref_start

offset      = stream_sync_sec - ref_sync_sec
stream_start = ref_start + offset
```

Full design: [`design_av_sync.md`](design_av_sync.md).

## Two different “masters”

| Master | Scope |
|---|---|
| Orbbec **Cam1 top-down** | Hardware trigger master among the three env Bolts |
| Kid Neon **scene** | Software gold for trim + aligning wearables and env exports |

Do not replace kid-scene gold with env top-down unless the project lead changes the SOP.

## Suggested folder layout per session

Example only — adapt to lab storage:

```text
sessions/
  2026-07-01_dyad01/
    raw/
      neon_kid/
      neon_parent/
      env_topdown.mkv
      env_adult_side.mkv
      env_toddler_side.mkv
      reolink.mp4          # optional
    preprocessing/
      sync.json
      fps_30/              # optional convert_fps outputs
      synced/              # sync_av outputs
      notes.txt            # who/when/quirks
```

## Related tools (this repo)

| Step | Tool |
|---|---|
| FPS | `convert_fps.py` — design in `design_fps_conversion.md` |
| Sync/trim media | `sync_av.py` — design in `design_av_sync.md` |
