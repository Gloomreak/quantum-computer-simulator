#!/usr/bin/env bash
# Полная проверка проекта (Linux/macOS).
#
#   bash scripts/check_all.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="python3"
if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
fi

echo "1/3 Проверка синтаксиса ..."
"$PYTHON" -m compileall -q app.py src tests scripts tools

echo "2/3 Автоматические тесты ..."
"$PYTHON" -m unittest discover -s tests -t .

echo "3/3 Проверка страниц интерфейса ..."
"$PYTHON" tools/ui_check.py

echo "Все проверки пройдены."
