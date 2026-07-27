#!/usr/bin/env bash
# Bootstrap the lab conda environment for HMET preprocessing (RA default).
#
# Usage:
#   ./setup.sh              # create/update conda env from environment.yml
#   ./setup.sh --check-only # only run scripts/check_env.py (use after activate)
#   ./setup.sh --system     # fallback: system Python + brew/apt ffmpeg (+ optional .venv)
#   ./setup.sh --system --no-venv
#
# After setup:
#   conda activate hmet-preprocess
#   python scripts/check_env.py

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

USE_CONDA=1
CHECK_ONLY=0
CREATE_VENV=1
INSTALL_FFMPEG=1

usage() {
  sed -n '2,13p' "$0" | sed -e 's/^# //' -e 's/^#//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --conda) USE_CONDA=1; CREATE_VENV=0; shift ;;
    --system) USE_CONDA=0; shift ;;
    --check-only) CHECK_ONLY=1; shift ;;
    --no-venv) CREATE_VENV=0; shift ;;
    --no-ffmpeg-install) INSTALL_FFMPEG=0; shift ;;
    -h|--help) usage 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

detect_os() {
  case "$(uname -s)" in
    Darwin) echo macos ;;
    Linux) echo linux ;;
    MINGW*|MSYS*|CYGWIN*) echo windows ;;
    *) echo unknown ;;
  esac
}

ensure_python() {
  if have python3; then
    PYTHON=python3
  elif have python; then
    PYTHON=python
  else
    echo "ERROR: Python 3.9+ not found. Install Python, then re-run." >&2
    exit 1
  fi

  if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "ERROR: Need Python 3.9+. Found: $("$PYTHON" --version 2>&1)" >&2
    exit 1
  fi
  echo "Using $($PYTHON --version 2>&1) at $(command -v "$PYTHON")"
}

install_ffmpeg_hint() {
  local os
  os="$(detect_os)"
  echo "ffmpeg / ffprobe not found on PATH."
  case "$os" in
    macos)
      if have brew && [[ "$INSTALL_FFMPEG" -eq 1 ]]; then
        echo "Installing ffmpeg via Homebrew..."
        brew install ffmpeg
      else
        echo "Install with: brew install ffmpeg"
        echo "Or use the lab default: ./setup.sh  (conda env includes ffmpeg)"
        exit 1
      fi
      ;;
    linux)
      if have apt-get && [[ "$INSTALL_FFMPEG" -eq 1 ]]; then
        echo "Installing ffmpeg via apt (may prompt for sudo)..."
        sudo apt-get update
        sudo apt-get install -y ffmpeg
      elif have dnf && [[ "$INSTALL_FFMPEG" -eq 1 ]]; then
        echo "Installing ffmpeg via dnf (may prompt for sudo)..."
        sudo dnf install -y ffmpeg
      else
        echo "Install ffmpeg with your package manager, or use conda:"
        echo "  ./setup.sh"
        exit 1
      fi
      ;;
    *)
      echo "On Windows, use Conda (lab default):"
      echo "  conda env create -f environment.yml"
      echo "  conda activate hmet-preprocess"
      exit 1
      ;;
  esac
}

ensure_ffmpeg() {
  if have ffmpeg && have ffprobe; then
    echo "Found $(ffmpeg -version 2>&1 | head -n1)"
    echo "Found ffprobe at $(command -v ffprobe)"
    return 0
  fi
  install_ffmpeg_hint
  if ! have ffmpeg || ! have ffprobe; then
    echo "ERROR: ffmpeg/ffprobe still missing after install attempt." >&2
    exit 1
  fi
}

setup_venv() {
  if [[ "$CREATE_VENV" -eq 0 ]]; then
    return 0
  fi
  if [[ -d "$ROOT/.venv" ]]; then
    echo "Virtualenv already exists: $ROOT/.venv"
  else
    echo "Creating virtualenv at $ROOT/.venv ..."
    "$PYTHON" -m venv "$ROOT/.venv"
  fi
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  PYTHON=python
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r "$ROOT/requirements.txt"
  echo "Activate later with: source .venv/bin/activate"
}

setup_conda() {
  local conda_cmd=""
  if have mamba; then
    conda_cmd=mamba
  elif have conda; then
    conda_cmd=conda
  else
    echo "ERROR: conda/mamba not found." >&2
    echo "Install Miniconda or Miniforge, then re-run ./setup.sh" >&2
    echo "  https://docs.conda.io/en/latest/miniconda.html" >&2
    echo "  https://github.com/conda-forge/miniforge" >&2
    exit 1
  fi

  if "$conda_cmd" env list | awk '{print $1}' | grep -qx 'hmet-preprocess'; then
    echo "Updating existing conda env hmet-preprocess ..."
    "$conda_cmd" env update -f "$ROOT/environment.yml" --prune
  else
    echo "Creating conda env from environment.yml ..."
    "$conda_cmd" env create -f "$ROOT/environment.yml"
  fi
  echo
  echo "Activate with: conda activate hmet-preprocess"
  echo "Then run:      python scripts/check_env.py"
}

run_checks() {
  local py="${PYTHON:-python3}"
  if [[ -x "$ROOT/.venv/bin/python" && "$CREATE_VENV" -eq 1 && "$USE_CONDA" -eq 0 ]]; then
    py="$ROOT/.venv/bin/python"
  fi
  echo
  echo "Running environment checks..."
  "$py" "$ROOT/scripts/check_env.py" --python "$py"
}

echo "=== HMET preprocessing setup ==="
echo "Repo: $ROOT"
echo

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  ensure_python
  run_checks
  exit 0
fi

if [[ "$USE_CONDA" -eq 1 ]]; then
  setup_conda
  echo
  echo "Setup finished. Activate the conda env, then verify:"
  echo "  conda activate hmet-preprocess"
  echo "  python scripts/check_env.py"
  exit 0
fi

echo "(Using --system fallback; lab default is conda via ./setup.sh)"
ensure_python
ensure_ffmpeg
setup_venv
run_checks

echo
echo "Setup complete."
echo "Next:"
if [[ "$CREATE_VENV" -eq 1 ]]; then
  echo "  source .venv/bin/activate"
fi
echo "  python convert_fps.py --help"
echo "  python sync_av.py --help"
echo "Docs: docs/getting-started.md"
