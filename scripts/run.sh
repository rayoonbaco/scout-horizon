#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m src.main --lookback-hours 24
python tools/build_cache.py
