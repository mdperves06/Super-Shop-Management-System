#!/usr/bin/env bash
# Starts the API on http://localhost:8000 (creates the venv and demo data on first run)
set -euo pipefail
cd "$(dirname "$0")/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt; }
[ -f shop.db ] || .venv/bin/python seed.py
exec .venv/bin/python -m uvicorn app.main:app --reload --port 8000
