@echo off
REM Starts the API on http://localhost:8000 (creates the venv and demo data on first run)
cd /d "%~dp0backend"
if not exist .venv ( python -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt )
if not exist shop.db ( .venv\Scripts\python seed.py )
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
