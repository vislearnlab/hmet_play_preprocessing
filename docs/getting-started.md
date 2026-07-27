# Getting started (RA handbook)

Welcome. This guide gets you from a fresh machine to a tested preprocessing run on real (or practice) session data.

## Day-1 checklist

- [ ] Miniconda or Miniforge installed
- [ ] Repo cloned / folder opened
- [ ] Conda env created (`./setup.sh` or `make setup`)
- [ ] `conda activate hmet-preprocess`
- [ ] `python scripts/check_env.py` passes
- [ ] `python convert_fps.py --help` and `python sync_av.py --help` work
- [ ] You have read [`pipeline-overview.md`](pipeline-overview.md) once
- [ ] You know where **raw** session data lives (do not write outputs into that folder)

## Environment setup (conda — required for RAs)

RAs use the shared **conda** environment `hmet-preprocess` from [`environment.yml`](../environment.yml). It pins **Python 3.9+** and **ffmpeg** together so every machine matches.

### 1. Install Conda (once per machine)

If `conda` is not already available, install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Miniforge](https://github.com/conda-forge/miniforge), then open a new terminal.

### 2. Create the lab env

```bash
cd hmet_play_preprocessing
./setup.sh
# or: make setup
# or: conda env create -f environment.yml
```

### 3. Activate and verify (every work session)

```bash
conda activate hmet-preprocess
python scripts/check_env.py
```

Expected: all checks `OK` (Python, ffmpeg, ffprobe, CLI help).

Update an existing env after `environment.yml` changes:

```bash
./setup.sh
# or: conda env update -f environment.yml --prune
```

Scripts still use only the Python standard library plus ffmpeg from the conda env. Future pip pins go in `requirements.txt` / `environment.yml`.

### Fallback (not for RAs)

If you cannot use conda, `./setup.sh --system` can install system ffmpeg and an optional `.venv`. Prefer fixing conda instead so your toolchain matches the lab.

## Your first FPS conversion (safe)

Use `--dry-run` first so nothing is written:

```bash
python3 convert_fps.py \
  -i /path/to/one_or_more_videos \
  --fps 30 \
  -o /path/to/out_30fps \
  --dry-run
```

Then run without `--dry-run`. Outputs are named like `clip_30fps.mp4`.

Useful flags:

| Flag | Meaning |
|---|---|
| `--recursive` | Walk subfolders when an input is a directory |
| `--overwrite` | Replace existing outputs |
| `--workers 4` | Parallel ffmpeg jobs |
| `--skip-if-matching` | Skip files already near target FPS |
| `--no-audio` | Drop audio tracks |

Design detail: [`design_fps_conversion.md`](design_fps_conversion.md).

## Your first sync/trim (safe)

### 1. Copy the example config

```bash
cp examples/sync_session.example.json /path/to/my_session_sync.json
```

### 2. Edit paths and numbers

Minimum you must set:

1. `reference.path` → kid Neon **scene** video  
2. `reference.trim_start_frame` / `trim_end_frame` → analysis window on kid scene (end exclusive)  
3. For each other video that needs aligning: `path`, `sync_frame` (or `sync_sec`), `align_to_ref_frame`

Field meanings: [`examples/README.md`](../examples/README.md) and [`design_av_sync.md`](design_av_sync.md).

### 3. Dry-run

```bash
python3 sync_av.py \
  -c /path/to/my_session_sync.json \
  -o /path/to/my_session_synced \
  --dry-run
```

Read the “Planned cuts” table. Check that start times are not wildly negative and durations match across streams.

### 4. Real run

```bash
python3 sync_av.py \
  -c /path/to/my_session_sync.json \
  -o /path/to/my_session_synced
```

### 5. Quick QA

- Open kid `*_synced` and one env `*_synced` side by side  
- Confirm the sync event lines up  
- Confirm the kept interaction segment is what you intended  

Full QA list: [`testing-guide.md`](testing-guide.md).

## Finding sync frames when there was no clap

Do **not** scrub two unrelated players for an hour if you can avoid it. See **Finding sync points** in [`design_av_sync.md`](design_av_sync.md).

Short version:

1. Audio correlation if both have audio  
2. Neon UTC for kid↔parent if clocks were synced — then visual QA  
3. Mark one sharp shared event; sync one env cam and inherit to the other env cams if hardware sync held  
4. Prefer a dual-scrub / frame-nudge workflow when marking manually  

## Data hygiene rules

1. **Never overwrite raw session folders.** Always write to a new output directory.  
2. Keep the sync JSON next to the session (or in a `preprocessing/` subfolder) so numbers are auditable.  
3. Note in a short text/CSV log: who ran the job, date, config path, output path, any oddities.  
4. If a command fails, copy the full terminal output when asking for help.

## When you are stuck

1. Re-run with `--dry-run` and read the plan/errors.  
2. Probe a file manually:

```bash
ffprobe -hide_banner /path/to/video
```

3. Check [`testing-guide.md`](testing-guide.md) “Common failures”.  
4. Ask the project lead before changing gold-standard conventions (kid scene as reference).
