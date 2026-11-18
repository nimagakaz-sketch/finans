#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ -d ".venv" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

echo "🚀 Запуск Семейного трекера финансов..."
$PYTHON -m backend.main
