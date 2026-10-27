#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".env" ]]; then
  echo "Missing scripts/.env"
  echo "Create it from .env.example, then configure your domain and commands."
  exit 1
fi

exec python3 ./script.py
