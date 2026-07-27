# Examples

## `sync_session.example.json`

Template for `sync_av.py`. Copy it per session and edit; do not overwrite the template in git with machine-specific paths unless intentional.

### Top-level shape

```json
{
  "reference": { ... },
  "streams": [ ... ]
}
```

### `reference` (kid Neon scene — required)

| Field | Required | Meaning |
|---|---|---|
| `path` | yes | Kid scene video (Cloud export `.mp4` or local file) |
| `trim_start_frame` | yes | Inclusive start frame on kid scene |
| `trim_end_frame` | yes | Exclusive end frame on kid scene |
| `fps` | no | Override probed FPS (Neon scene is typically 30) |
| `neon` | no | Metadata for future CSV tools; **ignored by `sync_av.py` today** |

### Each `streams[]` entry

| Field | Required | Meaning |
|---|---|---|
| `path` | yes | Video or audio file to align |
| `align_to_ref_frame` | yes | Kid-scene frame of the shared sync event |
| `sync_frame` **or** `sync_sec` **or** `sync_sample` | exactly one | Same event in this file |
| `name` | no | Output stem (default: file stem) → `<name>_synced.ext` |
| `type` | no | `video` or `audio` (usually inferred) |
| `neon` | no | Optional parent Neon paths for later CSV windowing |

### What to omit

- Kid eye / parent eye as clapped streams (same Neon clock as their scene video)  
- Reolink if the lab treats it as unsynced backup  
- Audio entries when you have none  

### Path resolution

Relative paths are resolved against:

1. The directory containing the config JSON  
2. Then the current working directory  

So if the config lives in `sessions/dyad01/preprocessing/sync.json`, you can write paths like `../raw/neon_kid/...mp4`.

### Minimal video-only example

```json
{
  "reference": {
    "path": "../raw/neon_kid/scene.mp4",
    "trim_start_frame": 300,
    "trim_end_frame": 9300,
    "fps": 30
  },
  "streams": [
    {
      "name": "parent_scene",
      "path": "../raw/neon_parent/scene.mp4",
      "sync_frame": 410,
      "align_to_ref_frame": 180
    },
    {
      "name": "env_topdown",
      "path": "../raw/env_topdown.mkv",
      "sync_frame": 95,
      "align_to_ref_frame": 180
    }
  ]
}
```

Run:

```bash
python3 sync_av.py -c sessions/dyad01/preprocessing/sync.json -o sessions/dyad01/preprocessing/synced --dry-run
```
