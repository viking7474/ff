#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
cd "$ROOT_DIR"

if [ ! -d "node_modules" ]; then
    echo "==> Installing workspace npm dependencies..."
    npm install
fi

echo "==> Running Winfox service tester..."
npm run test --workspace winfox-service-tester -- "$@"
