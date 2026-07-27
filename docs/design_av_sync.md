# Design: Multi-Stream AV Sync & Trim

> RA onboarding: start at the root [`README.md`](../README.md), then [`getting-started.md`](getting-started.md) and [`pipeline-overview.md`](pipeline-overview.md). This page is the design detail for `sync_av.py`.

## Goal

Align every video (and optional audio) stream in a recording session to the **kid’s scene-camera** timeline, then cut all streams to the **same logical window**. Outputs are equal-duration, time-aligned files for downstream HMET preprocessing.

Audio tracks are optional: video-only sessions are first-class.

## Design answers (short)

| Question | Recommendation |
|---|---|
| Best design? | **Config-driven session sync**: one gold reference + one shared trim + one sync point per other stream |
| How many parameters? | **3 session fields** + **~3 fields per secondary stream** (see below) |
| Different sync point per video? | **Yes — one manual sync point per stream**, not per frame. One correspondence is enough if FPS is constant and clocks do not drift |
| Trim the kid’s video too? | **Yes.** Trim is defined **only on the gold standard**; other streams inherit the window via their sync offset |

You do **not** specify a separate start/end for every camera. That duplicates work and drifts out of sync. You mark “this clap / flash / gesture is the same moment,” then apply one trim window on the kid cam.

## Motivation

Multi-camera / multi-mic captures rarely share a common start time. Manual sync (clapboard, light flash, visible clap) establishes correspondence. After sync, researchers usually want a shorter analysis window — including trimming the gold camera itself.

## Session stream inventory (HMET)

Aligned with environmental capture in [`recording-setup-spec.md`](../recording-setup-spec.md) and wearable capture on **Pupil Labs Neon** ([recording format](https://docs.pupil-labs.com/neon/data-collection/data-format/), [data streams](https://docs.pupil-labs.com/neon/data-collection/data-streams/)).

| Role | Streams | Notes |
|---|---|---|
| Kid Neon | scene video (**gold reference**), eye video / gaze timeseries | Same recording clock; see Neon section below |
| Parent Neon | scene video, eye video / gaze timeseries | Separate companion device → needs sync to kid |
| Environment (Orbbec) | `env_topdown`, `env_adult_side`, `env_toddler_side` | Cam1 top-down, Cam2 adult side, Cam3 toddler side |
| Optional context | `reolink` | Spec leaves open: synced channel vs loose backup |
| Optional audio | Neon scene-embedded mic and/or external lavs | Neon audio off by default in Companion |

```text
                    [env_topdown]
                         |
                         v
   [env_adult_side] → Adult   Toddler ← [env_toddler_side]
                         ↑         ↑
                   parent Neon   kid Neon  ← kid scene = software gold
                   (scene+eye)   (scene+eye)
```

### Two sync layers for environment cams (do not confuse them)

| Layer | What | Gold / master |
|---|---|---|
| **Hardware (env array)** | Orbbec sync hub + staggered IR triggers among the three Bolts | Spec: **Cam1 top-down = master** |
| **Software (session)** | Post-hoc align all files to one analysis timeline + shared trim | **Kid Neon scene video = gold** |

Hardware sync keeps the three environment depth/color streams mutually consistent. It does **not** replace software sync to the kid scene cam.

### Pupil Labs Neon wearables

Neon is not “two independent cameras that happen to be on a headset.” Scene and eye data from **one** recording share the Companion device clock and UTC nanosecond timestamps.

| Stream | Rate / shape | How it shows up on disk |
|---|---|---|
| Scene (world) video | 30 Hz, 1600×1200 | Cloud export: `<sectionId>_<start>-<end>.mp4` |
| Eye video | 200 Hz, 384×192 (L‖R concatenated) | Native / full recording exports (not always in “timeseries + scene video” Cloud bundles) |
| `world_timestamps.csv` | one row per scene frame | `timestamp [ns]` UTC for that world frame |
| `gaze.csv` / `3d_eye_states.csv` | up to 200 Hz | `timestamp [ns]` equals the **eye-video frame** time used for that sample |
| `info.json` | metadata | `start_time`, `duration` in nanoseconds; `wearer_name`, etc. |
| Audio | optional stereo | Muxed into scene video if enabled in Companion |

Folder naming (Cloud export): `<recording name>-<start of recording ID>/`.

#### What that means for sync parameters

| Pair | Manual clap / sync point? | Why |
|---|---|---|
| Kid scene ↔ kid eye / gaze | **No** (same Neon recording) | Already on one clock; map via `world_timestamps.csv` + gaze/eye timestamps |
| Parent scene ↔ parent eye / gaze | **No** (same Neon recording) | Same as kid |
| Kid Neon ↔ parent Neon | **Yes** (or NTP/UTC strategy) | Two Companion clocks |
| Kid Neon ↔ env cams / Reolink | **Yes** (typical) | Different recorders; env may lack Neon-quality UTC |

So you do **not** put `kid_eye` in the config as a separately clapped stream. You trim kid scene to `[T0, T1)`, then cut parent/env (and optionally export-native eye video) using the derived time window. Gaze/fixation CSVs should be filtered by the UTC window implied by `world_timestamps.csv` rows for frames `[T0, T1)`, not by inventing a second clap.

#### Neon ↔ Neon and Neon ↔ room timebases

Pupil documents that Companion UTC can drift; forcing an NTP sync on both phones (and the Windows capture PC) before the session keeps offsets small for ~hours ([time synchronization](https://docs.pupil-labs.com/neon/data-collection/time-synchronization/)). Even then, for behavioral work a **visible clap in both scene videos** remains the robust software anchor between kid and parent, and between kid and env.

Practical hybrid:

1. NTP-refresh Companions + Windows host before capture.  
2. One clap/flash visible to kid scene, parent scene, and at least one env cam.  
3. Gold trim on kid scene frames; propagate via sync points (and later via ns timestamps for Neon CSV products).

#### FPS note before frame indices

| Source | Native rate |
|---|---|
| Neon scene | 30 Hz |
| Neon eye | 200 Hz |
| Orbbec env (setup draft) | ~15 Hz |

Run `convert_fps.py` only when a **common video rate** is required. Do not assume frame index `N` on Neon scene equals frame `N` on an env cam without converting time through seconds/UTC.

### Typical parameter count (video sync stage)

- Session trim on kid scene: **3** fields  
- Manual sync streams: parent scene + 3 env (+ optional Reolink) → often **4–5** streams × 3 ≈ **12–15**  
- Kid/parent eye videos: **0 clap fields** if still inside their Neon recording (timestamp-derived trim later)  
- Optional audio: only external mics, or Neon scene audio already rides with scene video  

## Requirements

| Requirement | Detail |
|---|---|
| Gold standard | Kid’s scene-camera video is the reference timeline |
| Shared trim | `trim_start_frame` / `trim_end_frame` on the reference only |
| Per-stream sync | Each other stream has one sync correspondence to the reference |
| Video-only OK | Secondary list may be empty of audio; audio entries optional |
| Equal outputs | Every successful output covers the same duration on the session clock |
| Non-destructive | Write under `--output-dir`; never overwrite inputs by default |
| Dependency | System `ffmpeg` / `ffprobe` |

## Non-goals

- Automatic sync (audio cross-correlation, flash detection)
- Correcting long-term clock drift / timewarp (multi-point sync)
- Mixing all audio into one multitrack master (can be a later step)
- FPS conversion (use `convert_fps.py` before or after, consistently)

## Conceptual model

```text
Reference (kid scene cam)
  |---- sync event at ref frame R ----|
  |======== keep [T0, T1) ============|

Other stream
  |-- sync event at stream time S ----|
  offset = S_sec - R_sec
  keep [T0_sec + offset, T1_sec + offset)
```

All streams are cut to duration `T1_sec - T0_sec` on the session clock.

### Why one sync point per stream?

Assuming constant frame rate and no relative drift, a single shared event fully determines the offset:

`stream_time = reference_time + (S_sec - R_sec)`

Extra sync points only help if you need drift correction (out of scope).

### Frames vs seconds

- **Reference trim and reference sync** are specified in **frames** (natural for video annotation).
- **Secondary video sync** may use `sync_frame` (converted with that file’s FPS) or `sync_sec`.
- **Audio sync** should use `sync_sec` (or `sync_sample` + sample rate). Frames are ambiguous for audio-only files.

Internally everything is converted to **seconds** before calling ffmpeg.

## Parameter count

### Session (required)

| Field | Meaning |
|---|---|
| `reference.path` | Kid’s scene-camera video |
| `reference.trim_start_frame` | Inclusive start on gold timeline |
| `reference.trim_end_frame` | Exclusive end on gold timeline |

Optional session fields: `reference.fps` (override probe), `reference.sync_frame` default for align targets, output naming, encode settings.

### Per secondary stream (required each)

| Field | Meaning |
|---|---|
| `path` | Video or audio file |
| `sync_frame` **or** `sync_sec` | Moment in **this** file |
| `align_to_ref_frame` | Moment in **kid cam** that is the same event |

Optional: `name` / `role` (e.g. `wide`, `parent_cam`, `lav_mic`), `type` (`video` \| `audio`).

**Total:** 3 + 3N for N streams that need a **manual** sync point. With Neon, N is usually parent scene + env cams (not every eye camera).

### What you do *not* need per stream

- Separate `trim_start` / `trim_end` (derived)
- Per-frame sync tables
- A clap sync between kid scene and kid eye (same Neon recording)
- A clap sync between parent scene and parent eye (same Neon recording)
- Audio entries when unused (Neon mic is optional and embedded in scene video when on)
- Re-syncing env cams to each other when Orbbec hardware sync already did that (still sync the group to kid scene)

## Config format

JSON (stdlib-only; matches the rest of this repo). Full-session example: [`examples/sync_session.example.json`](../examples/sync_session.example.json).

Notes:

- Prefer Neon Cloud scene paths like `neon_kid/<section>_<t0>-<t1>.mp4` plus sibling `world_timestamps.csv` / `info.json` in the same folder for later CSV windowing.
- Use one shared clap/flash as `align_to_ref_frame` on **kid scene** for parent scene + env (+ Reolink if synced).
- Sync event can sit **before** the keep window (`trim_start_frame`). Preferred when the clap is pre-roll.
- Drop any stream block you do not have.
- `sync_av.py` today trims **media files**. Filtering Neon `gaze.csv` / fixations to the same window is a follow-on step using the UTC range from `world_timestamps.csv`.

## Pipeline

```text
config.json
   │
   ├─ probe reference FPS / duration
   ├─ ref_start_sec, ref_end_sec, duration_sec
   ├─ trim reference → out/kid_scene_synced.mp4
   └─ for each stream:
         compute stream_start_sec = ref_start_sec + (S_sec - R_sec)
         validate bounds (or pad)
         trim → out/<name>_synced.<ext>
```

### ffmpeg strategy

- Seek/trim with decode accuracy: `-i input -ss <start> -t <duration>` (more accurate than input-seek alone for edits).
- Video: re-encode defaults aligned with `convert_fps.py` (`libx264`, `yuv420p`, CRF 18) so cuts are frame-clean.
- Audio-only: write WAV (or copy/re-encode AAC into `.m4a` if requested).
- Embedded audio on secondary **videos**: keep (`-c:a aac`) or drop (`--no-audio`) — session mics are usually separate files.

## Edge cases

| Case | Behavior |
|---|---|
| `trim_end <= trim_start` | Fail fast |
| Derived `stream_start < 0` | Fail by default; optional `--allow-pad` adds leading black/silence |
| Derived end past EOF | Fail by default; optional pad trailing black/silence |
| Missing audio streams | Allowed; process reference + listed videos only |
| Same `align_to_ref_frame` for all | Typical (one clap visible/audible everywhere) |
| Different `align_to_ref_frame` per stream | Allowed if each stream used a different marked event |

## CLI interface

```bash
python sync_av.py \
  --config session01/sync.json \
  --output-dir session01/synced \
  [--dry-run] \
  [--overwrite] \
  [--allow-pad] \
  [--workers 1] \
  [--crf 18] \
  [--preset medium] \
  [--no-audio]
```

`--dry-run` prints computed start/end seconds per stream without writing.

## Module layout

```text
hmet_play_preprocessing/
  docs/design_av_sync.md
  sync_av.py
  examples/sync_session.example.json
```

## Key functions

| Function | Responsibility |
|---|---|
| `load_config(path)` | Parse/validate JSON |
| `probe_media(path)` | FPS, duration, has_video / has_audio |
| `compute_window(ref, stream)` | Map trim + sync → stream start + duration |
| `build_ffmpeg_cmd(...)` | Video or audio trim command |
| `sync_one(...)` | Run one trim; return result |
| `main()` | Orchestrate batch + summary |

## Finding sync points (no clap on disk)

Many early sessions will lack an intentional clap. Prefer the fastest method that your **available signals** allow; fall back to guided manual marking.

### Ranked options for this setup

| Priority | Method | When it works | Typical accuracy | Speed |
|---|---|---|---|---|
| 1 | **Audio cross-correlation** | Shared mic content on both files (Neon scene audio on, Reolink/room mic, etc.) | ~1 frame / few ms | Seconds (automatic) |
| 2 | **UTC / NTP timestamps** | Kid↔parent Neon after a forced Companion NTP refresh; optionally host PC if Orbbec times are wall-clock | ~1–10+ ms if fresh; worse if drifted | Seconds (compute) + one visual QA |
| 3 | **Hardware inherit** | Env cams already Orbbec-synced | Sync **one** env cam to kid; reuse offset for the other two after verifying | Fast |
| 4 | **Guided dual-scrub UI** | Always | 1 frame if event is sharp | Minutes per pair |
| 5 | **Motion / flash correlation** | Overlapping FOV (table action visible in kid scene + env) | Often ~1–3 frames | Semi-auto; needs tooling |
| 6 | **Blind multi-player watch** | Last resort | Operator-dependent | Slow, error-prone |

### Practical recommendation

**For already-recorded sessions without a clap:**

1. Check whether any pair has usable audio → run cross-correlation first.  
2. For **kid Neon ↔ parent Neon**, try UTC from `world_timestamps.csv` / `info.json` `start_time` if phones were time-synced; always **spot-check** one clear visual event.  
3. Sync **one** env cam (usually top-down) to kid scene with a sharp shared event (toy contact, hand clap visible as motion, light flicker). If Orbbec hardware sync held, copy that offset to the other two env files and verify once.  
4. Use a **dual-video offset scrubber** (side-by-side, nudge offset by 1 frame) instead of hunting in two separate players — same cognitive task, much faster and more accurate.

**What makes a good manual event** (if you must pick by eye):

- Short, high-contrast, visible in **both** FOVs  
- Prefer onset of contact (toy hits table, hands meet) over gradual motion  
- Avoid events only clear in one camera or during heavy occlusion  
- Record `(ref_frame, stream_frame)` for that onset — that is your sync pair

**Going forward (capture SOP):** do both — a **visible clap or phone-screen flash** at session start *and* keep Neon audio enabled when privacy allows. Flash is often better than clap for silent env depth/color streams; clap is better when audio correlation is available.

Automatic motion sync and a small offset-scrubber tool are listed under Future extensions; they are optional accelerators, not required for the config/`sync_av.py` path.

## Suggested annotation workflow

1. Decide export type per Neon wearer: Cloud “timeseries + scene video” (scene mp4 + CSVs) vs native (includes eye video).
2. Optionally normalize **video** FPS with `convert_fps.py` when cross-camera frame indices must match; keep Neon CSV work in UTC ns.
3. Play **kid scene**; note clap/flash frame `R` and keep range `[T0, T1)`.
4. Mark the same event on **parent scene** and each **env** cam (and Reolink if synced). Do **not** clap-sync eye cams inside a Neon recording.
5. Fill config; `sync_av.py --dry-run`; then run.
6. Derive UTC `[t0_ns, t1_ns)` from kid `world_timestamps.csv` for frames `[T0, T1)` and filter gaze tables to that window (after applying kid↔parent offset if not relying on UTC alone).
7. Spot-check: clap aligns on scene/env outputs; gaze overlays still land on the trimmed kid scene.

## Testing plan

1. Synthetic clips with a known flash at different absolute times → aligned outputs share flash at the same output timestamp.
2. Video-only config (no audio entries) succeeds.
3. Trim-only reference (empty `streams`) still writes trimmed kid cam.
4. Out-of-bounds offset fails clearly without `--allow-pad`.
5. `--dry-run` shows seconds math and writes nothing.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Variable frame-rate source | Probe `avg_frame_rate`; prefer CFR via `convert_fps.py` first |
| Keyframe-inaccurate copy trim | Default re-encode on video cuts |
| Drift over long sessions | Document limit; future multi-point sync |
| Operator frame off-by-one | Exclusive end frame; document inclusive/exclusive; dry-run |

## Future extensions

- Neon-aware windowing: given kid `world_timestamps.csv` + trim frames, emit UTC bounds and filter `gaze.csv` / fixations / IMU
- Inherit parent Neon eye/CSV trim from parent scene offset automatically
- Dual-pane **offset scrubber** CLI/UI (nudge sync by ±1 frame, write config fields)
- Optional **audio cross-correlation** helper to propose `sync_frame` / `sync_sec`
- Optional motion-energy correlation for overlapping env ↔ scene FOVs
- `--allow-pad` polish; CSV/JSONL sync audit manifest
- Optional mux of external lav onto a chosen video
- Neon `TimeOffsetEstimator` integration for live clock-offset logs
