# syntax=docker/dockerfile:1
#
# Образ учебного симулятора квантового компьютера.
#
# Сборка:  docker build -t quantum-computer-simulator:1.0.0 .
# Запуск:  docker run -d -p 8501:8501 --name quantum-simulator quantum-computer-simulator:1.0.0
#
# Всё, что нужно приложению, устанавливается на этапе сборки: на целевой
# машине не требуется Python, pip или какие-либо библиотеки.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# fonts-dejavu-core — резервный шрифт с кириллицей для системных утилит.
# Основной шрифт графиков поставляется в assets/fonts и не требует установки.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Только то, что нужно во время работы, плюс тесты и примеры.
COPY app.py ./
COPY src ./src
COPY examples ./examples
COPY assets ./assets
COPY docs ./docs
COPY scripts ./scripts
COPY tests ./tests
COPY README.md ./
COPY .streamlit ./.streamlit

# Приложение не работает от root.
RUN useradd --create-home --uid 1000 simulator \
    && chown -R simulator:simulator /app \
    && mkdir -p /home/simulator/.streamlit \
    && chown -R simulator:simulator /home/simulator

USER simulator

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"

# Порт и адрес передаются явно: переменные окружения тоже работают, но так
# команда запуска видна целиком в docker inspect.
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
