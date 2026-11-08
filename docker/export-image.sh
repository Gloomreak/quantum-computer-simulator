#!/usr/bin/env bash
# Сохранить готовый образ в файл для переноса на другой компьютер.
#
#   bash docker/export-image.sh
#
# Результат: dist/quantum-simulator-image.tar

set -euo pipefail

IMAGE="quantum-computer-simulator:1.0.0"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
TARGET="$DIST_DIR/quantum-simulator-image.tar"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker не найден." >&2
    exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Образ $IMAGE не найден. Сначала выполните docker/build-and-run.sh." >&2
    exit 1
fi

mkdir -p "$DIST_DIR"
echo "Сохраняю образ в $TARGET ..."
docker save -o "$TARGET" "$IMAGE"
echo "Готово: $TARGET"
