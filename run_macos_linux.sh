#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
# Install packages only when something is missing.
if ! "$PY" -c "import numpy, scipy, PIL, cv2, skimage, matplotlib, PyQt6" >/dev/null 2>&1; then
  "$PY" -m pip install -r requirements.txt
fi
"$PY" app.py
