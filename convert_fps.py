#!/usr/bin/env python3
"""Batch-convert videos to a common frame rate using ffmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")


@dataclass
class ConversionResult:
    source: Path
    output: Path | None
    source_fps: float | None
    target_fps: float
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


def discover_inputs(
    paths: Sequence[Path],
    extensions: Sequence[str],
    recursive: bool,
) -> list[Path]:
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    found: list[Path] = []

    for path in paths:
        if not path.exists():
            print(f"warning: path does not exist, skipping: {path}", file=sys.stderr)
            continue
        if path.is_file():
            if path.suffix.lower() in ext_set:
                found.append(path.resolve())
            else:
                print(
                    f"warning: unsupported extension, skipping: {path}",
                    file=sys.stderr,
                )
            continue
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for candidate in sorted(path.glob(pattern)):
                if candidate.is_file() and candidate.suffix.lower() in ext_set:
                    found.append(candidate.resolve())
            continue
        print(f"warning: not a file or directory, skipping: {path}", file=sys.stderr)

    # Preserve order while deduplicating
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def probe_fps(path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate,avg_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    try:
        payload = json.loads(completed.stdout)
        streams = payload.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        for key in ("avg_frame_rate", "r_frame_rate"):
            value = stream.get(key)
            fps = _parse_rate(value)
            if fps is not None and fps > 0:
                return fps
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


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


def unique_output_path(
    source: Path,
    output_dir: Path,
    target_fps: float,
    used_names: set[str],
) -> Path:
    fps_label = _fps_label(target_fps)
    stem = f"{source.stem}_{fps_label}fps"
    suffix = source.suffix.lower() or ".mp4"
    candidate_name = f"{stem}{suffix}"

    if candidate_name in used_names:
        parent = source.parent.name
        candidate_name = f"{parent}_{stem}{suffix}"

    counter = 2
    base = candidate_name
    while candidate_name in used_names:
        candidate_name = f"{Path(base).stem}_{counter}{suffix}"
        counter += 1

    used_names.add(candidate_name)
    return output_dir / candidate_name


def _fps_label(fps: float) -> str:
    if float(fps).is_integer():
        return str(int(fps))
    return f"{fps:g}"


def build_ffmpeg_cmd(
    source: Path,
    output: Path,
    target_fps: float,
    *,
    video_codec: str,
    crf: int,
    preset: str,
    include_audio: bool,
    overwrite: bool,
) -> list[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-i",
        str(source),
        "-vf",
        f"fps={target_fps}",
        "-c:v",
        video_codec,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
    ]
    if include_audio:
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.append("-an")
    cmd.append(str(output))
    return cmd


def convert_one(
    source: Path,
    output: Path,
    target_fps: float,
    *,
    video_codec: str,
    crf: int,
    preset: str,
    include_audio: bool,
    overwrite: bool,
    dry_run: bool,
    skip_if_matching: bool,
    fps_tolerance: float,
) -> ConversionResult:
    source_fps = probe_fps(source)

    if (
        skip_if_matching
        and source_fps is not None
        and abs(source_fps - target_fps) <= fps_tolerance
    ):
        return ConversionResult(
            source=source,
            output=None,
            source_fps=source_fps,
            target_fps=target_fps,
            ok=True,
            message="skipped (already at target fps)",
        )

    if output.exists() and not overwrite:
        return ConversionResult(
            source=source,
            output=output,
            source_fps=source_fps,
            target_fps=target_fps,
            ok=False,
            message=f"output exists (use --overwrite): {output}",
        )

    cmd = build_ffmpeg_cmd(
        source,
        output,
        target_fps,
        video_codec=video_codec,
        crf=crf,
        preset=preset,
        include_audio=include_audio,
        overwrite=overwrite,
    )

    if dry_run:
        return ConversionResult(
            source=source,
            output=output,
            source_fps=source_fps,
            target_fps=target_fps,
            ok=True,
            message="dry-run: " + " ".join(cmd),
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return ConversionResult(
            source=source,
            output=output,
            source_fps=source_fps,
            target_fps=target_fps,
            ok=False,
            message="ffmpeg not found",
        )

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        tail = err[-500:] if err else f"exit code {completed.returncode}"
        return ConversionResult(
            source=source,
            output=output,
            source_fps=source_fps,
            target_fps=target_fps,
            ok=False,
            message=tail,
        )

    return ConversionResult(
        source=source,
        output=output,
        source_fps=source_fps,
        target_fps=target_fps,
        ok=True,
        message="converted",
    )


def format_fps(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def print_summary(results: Iterable[ConversionResult]) -> None:
    rows = list(results)
    print("\nSummary")
    print("-" * 72)
    for result in rows:
        src_fps = format_fps(result.source_fps)
        status = "OK" if result.ok else "FAIL"
        out = str(result.output) if result.output else "-"
        print(
            f"[{status}] {result.source.name}  "
            f"{src_fps} -> {format_fps(result.target_fps)} fps  "
            f"{result.message}"
        )
        if result.output and result.ok and not result.message.startswith("dry-run"):
            print(f"       -> {out}")
    ok_count = sum(1 for r in rows if r.ok)
    fail_count = len(rows) - ok_count
    print("-" * 72)
    print(f"Done: {ok_count} succeeded, {fail_count} failed, {len(rows)} total.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert one or more videos to the same target frame rate using ffmpeg."
        )
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        required=True,
        type=Path,
        help="Video file(s) and/or directories containing videos",
    )
    parser.add_argument(
        "--fps",
        required=True,
        type=float,
        help="Target frame rate applied to every output video",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Directory for converted videos",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_EXTENSIONS),
        help=f"File extensions to include from directories (default: {', '.join(DEFAULT_EXTENSIONS)})",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when an input path is a directory",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing outputs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned conversions without writing files",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel ffmpeg jobs (default: 1)",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="x264 CRF quality (lower = higher quality; default: 18)",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="x264 preset (default: medium)",
    )
    parser.add_argument(
        "--video-codec",
        default="libx264",
        help="Video codec (default: libx264)",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Drop audio tracks from outputs",
    )
    parser.add_argument(
        "--skip-if-matching",
        action="store_true",
        help="Skip files whose source FPS is already near the target",
    )
    parser.add_argument(
        "--fps-tolerance",
        type=float,
        default=0.05,
        help="Tolerance for --skip-if-matching (default: 0.05)",
    )
    args = parser.parse_args(argv)
    if args.fps <= 0:
        parser.error("--fps must be positive")
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_ffmpeg()

    sources = discover_inputs(args.input, args.extensions, args.recursive)
    if not sources:
        print("No input videos found.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    jobs: list[tuple[Path, Path]] = []
    for source in sources:
        output = unique_output_path(source, args.output_dir, args.fps, used_names)
        jobs.append((source, output))

    print(f"Converting {len(jobs)} video(s) to {format_fps(args.fps)} fps")
    print(f"Output directory: {args.output_dir.resolve()}")

    results: list[ConversionResult] = []

    def run_job(pair: tuple[Path, Path]) -> ConversionResult:
        source, output = pair
        return convert_one(
            source,
            output,
            args.fps,
            video_codec=args.video_codec,
            crf=args.crf,
            preset=args.preset,
            include_audio=not args.no_audio,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            skip_if_matching=args.skip_if_matching,
            fps_tolerance=args.fps_tolerance,
        )

    if args.workers == 1:
        for job in jobs:
            result = run_job(job)
            status = "OK" if result.ok else "FAIL"
            print(f"[{status}] {result.source}")
            results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_job, job): job for job in jobs}
            for future in as_completed(futures):
                result = future.result()
                status = "OK" if result.ok else "FAIL"
                print(f"[{status}] {result.source}")
                results.append(result)
        # Stable summary order matching input discovery
        by_source = {r.source: r for r in results}
        results = [by_source[src] for src, _ in jobs]

    print_summary(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
