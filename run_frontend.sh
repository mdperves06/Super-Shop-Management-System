#!/usr/bin/env bash
# Starts the web app on http://localhost:3000
set -euo pipefail
cd "$(dirname "$0")/frontend"
[ -f .env.local ] || cp .env.example .env.local
[ -d node_modules ] || npm install
exec npm run dev
