#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
WITH_CATALOG=false
if [[ "${1:-}" == "--catalog" ]]; then WITH_CATALOG=true
elif [[ $# -ne 0 ]]; then echo "Usage: bash scripts/setup-mac.sh [--catalog]" >&2; exit 2; fi
PYTHON_BIN="${KYP_PYTHON:-python3.14}"
command -v "$PYTHON_BIN" >/dev/null || { echo 'Install Python 3.14 first (see MACBOOK-SETUP.md).' >&2; exit 1; }
command -v node >/dev/null || { echo 'Install Node 24 first.' >&2; exit 1; }
command -v npm >/dev/null || { echo 'npm is required.' >&2; exit 1; }
"$PYTHON_BIN" -c 'import sys; assert sys.version_info[:2] == (3,14), "Use Python 3.14 for this tested dependency set"'
node -e 'if(Number(process.versions.node.split(".")[0])<24) throw Error("Use Node 24 or later")'
if [[ ! -d backend/.venv ]]; then "$PYTHON_BIN" -m venv backend/.venv; fi
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm ci --prefix backend/ocr-runtime
node backend/ocr-runtime/setup-model.mjs
npm ci --prefix mobile
if [[ ! -e .env ]]; then cp .env.example .env; fi
if [[ ! -e mobile/.env.local ]]; then
    printf '%s\n' 'EXPO_PUBLIC_API_URL=http://127.0.0.1:8001' > mobile/.env.local
fi
if [[ "$WITH_CATALOG" == true ]]; then
    (
        cd backend
        .venv/bin/python -B -m kyp.ingest --db data/kyp.sqlite3
        .venv/bin/python -B -m kyp.cosing --db data/kyp.sqlite3
        .venv/bin/python -B -m kyp.food --db data/kyp.sqlite3
    )
    echo 'Catalog imported as drafts. Review sources/descriptions before publication; see MACBOOK-SETUP.md.'
fi
npm run typecheck --prefix mobile
npm run lint --prefix mobile
printf '\n%s\n' 'Setup complete. Follow MACBOOK-SETUP.md to start the API/mobile app and initialize Git.'
