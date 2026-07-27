#!/usr/bin/env python3
"""Sync and trim multi-stream AV sessions to a gold-standard reference video."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


@dataclass
class MediaInfo:
    path: Path
    duration_sec: float | None
    fps: float | None
    has_video: bool
    has_audio: bool
    sample_rate: int | None


@dataclass
class ReferenceSpec:
    path: Path
    trim_start_frame: int
    trim_end_frame: int
    fps_override: float | None


@dataclass
class StreamSpec:
    name: str
    path: Path
    align_to_ref_frame: int
    sync_frame: float | None
    sync_sec: float | None
    sync_sample: int | None
    type_hint: str | None


@dataclass
class PlannedCut:
    name: str
    source: Path
    output: Path
    kind: str  # "video" | "audio"
    start_sec: float
    duration_sec: float
    align_to_ref_frame: int
    source_sync_sec: float
    ref_sync_sec: float
    is_reference: bool
    source_duration_sec: float | None


@dataclass
class SyncResult:
    plan: PlannedCut
    ok: bool
    message: str


def ensure_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            f"Required tool(s) not found on PATH: {names}. "
            "Install ffmpeg (e.g. `brew install ffmpeg`) and retry."
        )


def _parse_rate(value: object) -> float | None:
    if not isinstance(value, str) or not value or value == "0/0":
        return None
    if "/" in value:
        num_s, den_s = value.split("/", 1)
        num, den = float(num_s), float(den_s)
        if den == 0:
            return None
        return num / den
    return float(value)


def probe_media(path: Path) -> MediaInfo:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,r_frame_rate,avg_frame_rate,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        err = (completed.stderr or "").strip() or f"ffprobe exit {completed.returncode}"
        raise RuntimeError(f"ffprobe failed for {path}: {err}")

    payload = json.loads(completed.stdout)
    duration = None
    fmt = payload.get("format") or {}
    if fmt.get("duration") not in (None, "N/A"):
        duration = float(fmt["duration"])

    has_video = False
    has_audio = False
    fps = None
    sample_rate = None
    for stream in payload.get("streams") or []:
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            has_video = True
            if fps is None:
                for key in ("avg_frame_rate", "r_frame_rate"):
                    candidate = _parse_rate(stream.get(key))
                    if candidate is not None and candidate > 0:
                        fps = candidate
                        break
        elif codec_type == "audio":
            has_audio = True
            if sample_rate is None and stream.get("sample_rate"):
                sample_rate = int(float(stream["sample_rate"]))

    return MediaInfo(
        path=path,
        duration_sec=duration,
        fps=fps,
        has_video=has_video,
        has_audio=has_audio,
        sample_rate=sample_rate,
    )


def load_config(path: Path) -> tuple[ReferenceSpec, list[StreamSpec]]:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON config {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SystemExit("Config root must be a JSON object")

    ref_raw = raw.get("reference")
    if not isinstance(ref_raw, dict):
        raise SystemExit("Config must include a 'reference' object")

    try:
        ref_path = Path(ref_raw["path"])
        trim_start = int(ref_raw["trim_start_frame"])
        trim_end = int(ref_raw["trim_end_frame"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(
            "reference requires path, trim_start_frame, trim_end_frame"
        ) from exc

    if trim_end <= trim_start:
        raise SystemExit("reference.trim_end_frame must be > trim_start_frame")
    if trim_start < 0:
        raise SystemExit("reference.trim_start_frame must be >= 0")

    fps_override = ref_raw.get("fps")
    if fps_override is not None:
        fps_override = float(fps_override)
        if fps_override <= 0:
            raise SystemExit("reference.fps must be positive when set")

    reference = ReferenceSpec(
        path=ref_path,
        trim_start_frame=trim_start,
        trim_end_frame=trim_end,
        fps_override=fps_override,
    )

    streams_raw = raw.get("streams") or []
    if not isinstance(streams_raw, list):
        raise SystemExit("'streams' must be a list when present")

    streams: list[StreamSpec] = []
    used_names: set[str] = set()
    for idx, item in enumerate(streams_raw):
        if not isinstance(item, dict):
            raise SystemExit(f"streams[{idx}] must be an object")
        try:
            stream_path = Path(item["path"])
            align = int(item["align_to_ref_frame"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(
                f"streams[{idx}] requires path and align_to_ref_frame"
            ) from exc

        sync_frame = item.get("sync_frame")
        sync_sec = item.get("sync_sec")
        sync_sample = item.get("sync_sample")
        present = [v is not None for v in (sync_frame, sync_sec, sync_sample)]
        if sum(present) != 1:
            raise SystemExit(
                f"streams[{idx}] must set exactly one of "
                "sync_frame, sync_sec, or sync_sample"
            )

        name = str(item.get("name") or stream_path.stem)
        if name in used_names:
            raise SystemExit(f"Duplicate stream name: {name}")
        used_names.add(name)

        type_hint = item.get("type")
        if type_hint is not None:
            type_hint = str(type_hint).lower()
            if type_hint not in {"video", "audio"}:
                raise SystemExit(f"streams[{idx}].type must be 'video' or 'audio'")

        streams.append(
            StreamSpec(
                name=name,
                path=stream_path,
                align_to_ref_frame=align,
                sync_frame=float(sync_frame) if sync_frame is not None else None,
                sync_sec=float(sync_sec) if sync_sec is not None else None,
                sync_sample=int(sync_sample) if sync_sample is not None else None,
                type_hint=type_hint,
            )
        )

    return reference, streams


def resolve_path(path: Path, config_dir: Path) -> Path:
    if path.is_absolute():
        return path
    candidate = (config_dir / path).resolve()
    if candidate.exists():
        return candidate
    cwd_candidate = path.resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return candidate


def infer_kind(spec: StreamSpec, info: MediaInfo) -> str:
    if spec.type_hint:
        return spec.type_hint
    suffix = spec.path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS and not info.has_video:
        return "audio"
    if info.has_video:
        return "video"
    if info.has_audio:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise RuntimeError(f"Could not infer media type for {spec.path}")


def stream_sync_sec(spec: StreamSpec, info: MediaInfo) -> float:
    if spec.sync_sec is not None:
        return spec.sync_sec
    if spec.sync_frame is not None:
        if not info.fps or info.fps <= 0:
            raise RuntimeError(
                f"Cannot convert sync_frame for {spec.path}: FPS unknown. "
                "Set sync_sec instead, or ensure the file has a video stream."
            )
        return spec.sync_frame / info.fps
    if spec.sync_sample is not None:
        if not info.sample_rate or info.sample_rate <= 0:
            raise RuntimeError(
                f"Cannot convert sync_sample for {spec.path}: sample rate unknown. "
                "Set sync_sec instead."
            )
        return spec.sync_sample / float(info.sample_rate)
    raise RuntimeError(f"No sync point for {spec.path}")


def build_plans(
    reference: ReferenceSpec,
    streams: Sequence[StreamSpec],
    config_dir: Path,
    output_dir: Path,
    allow_pad: bool,
) -> list[PlannedCut]:
    ref_path = resolve_path(reference.path, config_dir)
    if not ref_path.exists():
        raise SystemExit(f"Reference video not found: {ref_path}")

    ref_info = probe_media(ref_path)
    ref_fps = reference.fps_override or ref_info.fps
    if not ref_fps or ref_fps <= 0:
        raise SystemExit(
            "Could not determine reference FPS. Set reference.fps in the config."
        )
    if not ref_info.has_video:
        raise SystemExit(f"Reference has no video stream: {ref_path}")

    ref_start_sec = reference.trim_start_frame / ref_fps
    ref_end_sec = reference.trim_end_frame / ref_fps
    duration_sec = ref_end_sec - ref_start_sec
    if duration_sec <= 0:
        raise SystemExit("Computed reference duration must be positive")

    if ref_info.duration_sec is not None and ref_end_sec > ref_info.duration_sec + 1e-3:
        raise SystemExit(
            f"trim_end_frame exceeds reference duration "
            f"({ref_end_sec:.3f}s > {ref_info.duration_sec:.3f}s)"
        )

    plans: list[PlannedCut] = [
        PlannedCut(
            name="reference",
            source=ref_path,
            output=output_dir
            / f"{ref_path.stem}_synced{ref_path.suffix.lower() or '.mp4'}",
            kind="video",
            start_sec=ref_start_sec,
            duration_sec=duration_sec,
            align_to_ref_frame=reference.trim_start_frame,
            source_sync_sec=ref_start_sec,
            ref_sync_sec=ref_start_sec,
            is_reference=True,
            source_duration_sec=ref_info.duration_sec,
        )
    ]

    used_out_names = {plans[0].output.name}

    for spec in streams:
        source = resolve_path(spec.path, config_dir)
        if not source.exists():
            raise SystemExit(f"Stream not found: {source}")
        info = probe_media(source)
        kind = infer_kind(spec, info)
        sync_sec = stream_sync_sec(spec, info)
        ref_sync_sec = spec.align_to_ref_frame / ref_fps
        offset = sync_sec - ref_sync_sec
        start_sec = ref_start_sec + offset
        end_sec = start_sec + duration_sec

        if start_sec < -1e-6 and not allow_pad:
            raise SystemExit(
                f"Stream '{spec.name}' starts before file begin "
                f"(start={start_sec:.3f}s). Fix sync points or pass --allow-pad."
            )
        if (
            info.duration_sec is not None
            and end_sec > info.duration_sec + 1e-3
            and not allow_pad
        ):
            raise SystemExit(
                f"Stream '{spec.name}' trim extends past EOF "
                f"(end={end_sec:.3f}s, duration={info.duration_sec:.3f}s). "
                "Fix sync/trim or pass --allow-pad."
            )

        if kind == "audio":
            if source.suffix.lower() in AUDIO_EXTENSIONS:
                out_suffix = source.suffix.lower()
            else:
                out_suffix = ".wav"
        else:
            out_suffix = source.suffix.lower() or ".mp4"

        out_name = f"{spec.name}_synced{out_suffix}"
        if out_name in used_out_names:
            raise SystemExit(f"Output name collision: {out_name}")
        used_out_names.add(out_name)

        plans.append(
            PlannedCut(
                name=spec.name,
                source=source,
                output=output_dir / out_name,
                kind=kind,
                start_sec=start_sec,
                duration_sec=duration_sec,
                align_to_ref_frame=spec.align_to_ref_frame,
                source_sync_sec=sync_sec,
                ref_sync_sec=ref_sync_sec,
                is_reference=False,
                source_duration_sec=info.duration_sec,
            )
        )

    return plans


def _pad_amounts(plan: PlannedCut) -> tuple[float, float, float]:
    """Return (lead_pad_sec, source_start_sec, trail_pad_sec)."""
    lead = max(0.0, -plan.start_sec)
    source_start = max(0.0, plan.start_sec)
    available = None
    if plan.source_duration_sec is not None:
        available = max(0.0, plan.source_duration_sec - source_start)
    if available is None:
        trail = 0.0
    else:
        trail = max(0.0, plan.duration_sec - lead - available)
    return lead, source_start, trail


def build_ffmpeg_cmd(
    plan: PlannedCut,
    *,
    video_codec: str,
    crf: int,
    preset: str,
    include_embedded_audio: bool,
    overwrite: bool,
    allow_pad: bool,
) -> list[str]:
    lead, source_start, trail = _pad_amounts(plan)
    if (lead > 1e-6 or trail > 1e-6) and not allow_pad:
        raise RuntimeError(
            f"Padding required for '{plan.name}' but --allow-pad was not set "
            f"(lead={lead:.3f}s, trail={trail:.3f}s)"
        )

    take_from_source = plan.duration_sec - lead - trail
    if take_from_source < -1e-6:
        raise RuntimeError(f"Invalid cut math for '{plan.name}'")
    take_from_source = max(0.0, take_from_source)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-i",
        str(plan.source),
    ]

    if plan.kind == "video":
        vf: list[str] = []
        if source_start > 0 or take_from_source < (plan.source_duration_sec or 1e18):
            # trim timeline then reset timestamps
            end = source_start + take_from_source
            vf.append(f"trim=start={source_start:.6f}:end={end:.6f}")
            vf.append("setpts=PTS-STARTPTS")
        if lead > 0 or trail > 0:
            parts = ["tpad"]
            if lead > 0:
                parts.append(f"start_mode=clone:start_duration={lead:.6f}")
            if trail > 0:
                parts.append(f"stop_mode=clone:stop_duration={trail:.6f}")
            vf.append(":".join(parts))

        if vf:
            cmd.extend(["-vf", ",".join(vf)])
        else:
            cmd.extend(["-ss", f"{source_start:.6f}", "-t", f"{plan.duration_sec:.6f}"])

        cmd.extend(
            [
                "-c:v",
                video_codec,
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
            ]
        )

        # Embedded audio + pad is easy to get wrong; keep audio only on simple cuts.
        if include_embedded_audio and lead == 0 and trail == 0:
            cmd.extend(
                [
                    "-af",
                    (
                        f"atrim=start={source_start:.6f}:"
                        f"end={source_start + take_from_source:.6f},"
                        "asetpts=PTS-STARTPTS"
                    ),
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                ]
            )
        else:
            cmd.append("-an")

        cmd.extend(["-t", f"{plan.duration_sec:.6f}", str(plan.output)])
        return cmd

    # Audio-only
    af_parts: list[str] = []
    end = source_start + take_from_source
    af_parts.append(f"atrim=start={source_start:.6f}:end={end:.6f}")
    af_parts.append("asetpts=PTS-STARTPTS")
    if lead > 0:
        delay_ms = max(1, int(round(lead * 1000.0)))
        af_parts.append(f"adelay={delay_ms}|{delay_ms}")
    if trail > 0:
        af_parts.append(f"apad=pad_dur={trail:.6f}")
    af_parts.append(f"atrim=0:{plan.duration_sec:.6f}")
    af_parts.append("asetpts=PTS-STARTPTS")
    cmd.extend(["-af", ",".join(af_parts)])

    out_ext = plan.output.suffix.lower()
    if out_ext == ".wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif out_ext == ".mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-t", f"{plan.duration_sec:.6f}", str(plan.output)])
    return cmd


def sync_one(
    plan: PlannedCut,
    *,
    video_codec: str,
    crf: int,
    preset: str,
    include_embedded_audio: bool,
    overwrite: bool,
    dry_run: bool,
    allow_pad: bool,
) -> SyncResult:
    if plan.output.exists() and not overwrite and not dry_run:
        return SyncResult(
            plan=plan,
            ok=False,
            message=f"output exists (use --overwrite): {plan.output}",
        )

    try:
        cmd = build_ffmpeg_cmd(
            plan,
            video_codec=video_codec,
            crf=crf,
            preset=preset,
            include_embedded_audio=include_embedded_audio,
            overwrite=overwrite,
            allow_pad=allow_pad,
        )
    except Exception as exc:  # noqa: BLE001
        return SyncResult(plan=plan, ok=False, message=str(exc))

    if dry_run:
        return SyncResult(
            plan=plan,
            ok=True,
            message=(
                f"dry-run start={plan.start_sec:.3f}s dur={plan.duration_sec:.3f}s :: "
                + " ".join(cmd)
            ),
        )

    plan.output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        tail = err[-500:] if err else f"exit code {completed.returncode}"
        return SyncResult(plan=plan, ok=False, message=tail)

    return SyncResult(plan=plan, ok=True, message="synced")


def print_plan_table(plans: Sequence[PlannedCut]) -> None:
    print("\nPlanned cuts")
    print("-" * 88)
    for plan in plans:
        role = "REF" if plan.is_reference else plan.kind.upper()
        print(
            f"[{role}] {plan.name:16}  "
            f"start={plan.start_sec:8.3f}s  dur={plan.duration_sec:8.3f}s  "
            f"sync_src={plan.source_sync_sec:.3f}s ↔ ref={plan.ref_sync_sec:.3f}s"
        )
        print(f"       {plan.source}")
        print(f"    -> {plan.output}")
    print("-" * 88)


def print_summary(results: Sequence[SyncResult]) -> None:
    print("\nSummary")
    print("-" * 72)
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.plan.name}: {result.message}")
    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count
    print("-" * 72)
    print(f"Done: {ok_count} succeeded, {fail_count} failed, {len(results)} total.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Trim the kid scene-camera gold standard and sync/trim all other "
            "video/audio streams to the same window."
        )
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="JSON session config (see examples/sync_session.example.json)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Directory for synced outputs",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite outputs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned cuts / commands without writing",
    )
    parser.add_argument(
        "--allow-pad",
        action="store_true",
        help="Pad with cloned frames / silence if a stream does not fully cover the window",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel ffmpeg jobs (default: 1)",
    )
    parser.add_argument("--crf", type=int, default=18, help="x264 CRF (default: 18)")
    parser.add_argument("--preset", default="medium", help="x264 preset (default: medium)")
    parser.add_argument(
        "--video-codec",
        default="libx264",
        help="Video codec (default: libx264)",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Drop embedded audio from video outputs (separate audio streams still processed)",
    )
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_ffmpeg()

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 1

    reference, streams = load_config(args.config)
    config_dir = args.config.parent.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        plans = build_plans(
            reference,
            streams,
            config_dir=config_dir,
            output_dir=args.output_dir,
            allow_pad=args.allow_pad,
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to build sync plan: {exc}", file=sys.stderr)
        return 1

    print(
        f"Session sync: {len(plans)} output(s) "
        f"(reference trim frames "
        f"{reference.trim_start_frame}..{reference.trim_end_frame})"
    )
    print_plan_table(plans)

    results: list[SyncResult] = []

    def run_one(plan: PlannedCut) -> SyncResult:
        return sync_one(
            plan,
            video_codec=args.video_codec,
            crf=args.crf,
            preset=args.preset,
            include_embedded_audio=not args.no_audio,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            allow_pad=args.allow_pad,
        )

    if args.workers == 1:
        for plan in plans:
            result = run_one(plan)
            status = "OK" if result.ok else "FAIL"
            print(f"[{status}] {result.plan.name}")
            results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_one, plan): plan for plan in plans}
            by_name: dict[str, SyncResult] = {}
            for future in as_completed(futures):
                result = future.result()
                status = "OK" if result.ok else "FAIL"
                print(f"[{status}] {result.plan.name}")
                by_name[result.plan.name] = result
        results = [by_name[p.name] for p in plans]

    print_summary(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
