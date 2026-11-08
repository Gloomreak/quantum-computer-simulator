#!/usr/bin/env bash
# Сборка образа и запуск контейнера (Linux/macOS).
#
#   bash docker/build-and-run.sh
#
# Требуется Docker Engine или Docker Desktop. Первая сборка требует
# интернета, повторные запуски — нет.

set -euo pipefail

IMAGE="quantum-computer-simulator:1.0.0"
CONTAINER="quantum-simulator"
PORT="8501"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker не найден. Установите Docker и повторите запуск." >&2
    exit 1
fi

cd "$PROJECT_ROOT"

echo "Сборка образа $IMAGE ..."
docker build -t "$IMAGE" .

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Удаляю предыдущий контейнер $CONTAINER ..."
    docker rm -f "$CONTAINER" >/dev/null
fi

echo "Запуск контейнера ..."
docker run -d --name "$CONTAINER" -p "${PORT}:8501" --restart unless-stopped "$IMAGE" >/dev/null

echo "Ожидание готовности приложения ..."
for _ in $(seq 1 30); do
    sleep 2
    if curl -fsS "http://127.0.0.1:${PORT}/_stcore/health" >/dev/null 2>&1; then
        echo "Готово. Откройте в браузере: http://localhost:${PORT}"
        exit 0
    fi
done

echo "Контейнер запущен, но приложение ещё не отвечает. Проверьте: docker logs $CONTAINER" >&2
