#!/usr/bin/env bash
# Загрузить образ из файла и запустить контейнер (Linux/macOS).
#
#   bash docker/load-and-run.sh [путь-к-образу.tar]
#
# Нужен только Docker: ни Python, ни pip, ни интернет не требуются.

set -euo pipefail

IMAGE="quantum-computer-simulator:1.0.0"
CONTAINER="quantum-simulator"
PORT="${PORT:-8501}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${1:-$PROJECT_ROOT/dist/quantum-simulator-image.tar}"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker не найден. Установите Docker." >&2
    exit 1
fi
if [[ ! -f "$ARCHIVE" ]]; then
    echo "Файл образа не найден: $ARCHIVE" >&2
    exit 1
fi

echo "Загружаю образ из $ARCHIVE ..."
docker load -i "$ARCHIVE"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker rm -f "$CONTAINER" >/dev/null
fi

echo "Запуск контейнера ..."
docker run -d --name "$CONTAINER" -p "${PORT}:8501" --restart unless-stopped "$IMAGE" >/dev/null

echo "Готово. Откройте в браузере: http://localhost:${PORT}"
