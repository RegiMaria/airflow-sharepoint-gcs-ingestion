#!/usr/bin/env bash
# scripts/stop.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🛑 Parando ambiente..."

if [ "${1:-}" = "--clean" ]; then
  echo "⚠️  Modo --clean: removendo volumes (reset total do banco de dados)"
  docker-compose down -v
else
  docker-compose down
  echo "✅ Containers parados. Volumes preservados."
  echo "   Para reset total: ./scripts/stop.sh --clean"
fi
