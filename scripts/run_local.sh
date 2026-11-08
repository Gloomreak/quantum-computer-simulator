#!/usr/bin/env bash
# Локальный запуск без Docker (Linux/macOS).
#
#   bash scripts/run_local.sh
#
# Если окружение .venv уже создано и зависимости установлены, скрипт сразу
# запускает приложение и не обращается в интернет. Иначе создаёт .venv и
# устанавливает зависимости (нужен интернет один раз).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python не найден. Установите Python 3.11+." >&2
    exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Создаю виртуальное окружение .venv ..."
    "$PYTHON" -m venv .venv
fi

if .venv/bin/python -c "import streamlit" >/dev/null 2>&1; then
    echo "Окружение готово, установка зависимостей не требуется."
else
    echo "Устанавливаю зависимости (нужен интернет) ..."
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

echo "Запуск приложения: http://localhost:8501"
exec .venv/bin/python -m streamlit run app.py
