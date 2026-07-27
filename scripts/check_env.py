#!/usr/bin/env python3
"""Verify that this machine can run the HMET preprocessing CLIs.

Checks Python version, ffmpeg/ffprobe on PATH, and that convert_fps /
sync_av respond to --help. Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 9)
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ("convert_fps.py", "sync_av.py")


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> None:
    print(f" FAIL {msg}", file=sys.stderr)


def check_python() -> bool:
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < MIN_PYTHON:
        _fail(
            f"Python {version} (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"
        )
        return False
    _ok(f"Python {version} ({sys.executable})")
    return True


def _tool_version(name: str) -> str | None:
    path = shutil.which(name)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [name, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    # ffmpeg prints version on stderr; some builds use stdout
    text = (proc.stderr or proc.stdout or "").strip()
    first = text.splitlines()[0] if text else path
    return first


def check_ffmpeg_tools() -> bool:
    ok = True
    for name in ("ffmpeg", "ffprobe"):
        version = _tool_version(name)
        if version is None:
            _fail(f"{name} not found on PATH")
            ok = False
        else:
            _ok(f"{name}: {version}")
    return ok


def check_clis(python: str) -> bool:
    ok = True
    for script in SCRIPTS:
        path = REPO_ROOT / script
        if not path.is_file():
            _fail(f"missing {script}")
            ok = False
            continue
        try:
            proc = subprocess.run(
                [python, str(path), "--help"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            _fail(f"{script} --help: {exc}")
            ok = False
            continue
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            _fail(f"{script} --help exited {proc.returncode}: {err}")
            ok = False
        else:
            _ok(f"{script} --help")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check HMET preprocessing environment prerequisites."
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to smoke-test CLIs (default: this one)",
    )
    args = parser.parse_args(argv)

    print("HMET preprocessing environment check")
    print(f"Repo: {REPO_ROOT}")
    print()

    results = [
        check_python(),
        check_ffmpeg_tools(),
        check_clis(args.python),
    ]

    print()
    if all(results):
        print("All checks passed. Ready to run convert_fps.py / sync_av.py.")
        return 0

    print("Some checks failed. See docs/getting-started.md or run ./setup.sh")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
