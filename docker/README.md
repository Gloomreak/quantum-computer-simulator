# Запуск в Docker

Приложение упаковано в образ так, что на целевом компьютере не нужны ни
Python, ни библиотеки: достаточно Docker. Все расчёты выполняются внутри
контейнера, приложение доступно по адресу <http://localhost:8501>.

## Что нужно на компьютере

- Windows 10/11: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  с включённым WSL 2 (при установке Docker Desktop предлагает это сам).
- macOS: Docker Desktop.
- Linux: Docker Engine (пакет `docker.io` или `docker-ce`) + `docker compose`.

Проверка: `docker --version` и `docker info` должны завершаться без ошибок.

## Быстрый старт (интернет нужен только при первой сборке)

### Windows (PowerShell)

```powershell
cd путь\к\quantum-computer-simulator
powershell -ExecutionPolicy Bypass -File docker\build-and-run.ps1
```

### Linux / macOS

```bash
cd путь/к/quantum-computer-simulator
bash docker/build-and-run.sh
```

Скрипт соберёт образ `quantum-computer-simulator:1.0.0`, запустит контейнер
`quantum-simulator` на порту 8501 и дождётся, пока приложение ответит.

### Через docker compose

```bash
docker compose up -d --build
```

Остановить: `docker compose down`. Посмотреть журнал: `docker compose logs -f`.

## Перенос на другой ноутбук без интернета

1. На машине, где образ уже собран:

   ```powershell
   powershell -ExecutionPolicy Bypass -File docker\export-image.ps1
   ```

   (Linux/macOS: `bash docker/export-image.sh`)

   Появится файл `dist/quantum-simulator-image.tar` (≈ 0,6–1,0 ГБ).

2. Скопируйте этот файл и папку `docker` на целевой ноутбук (флешка, сеть —
   как удобно).

3. На целевом ноутбуке с установленным Docker:

   ```powershell
   powershell -ExecutionPolicy Bypass -File docker\load-and-run.ps1 -Archive dist\quantum-simulator-image.tar
   ```

   (Linux/macOS: `bash docker/load-and-run.sh /путь/к/quantum-simulator-image.tar`)

Образ загрузится из файла и контейнер запустится. Скачивание библиотек и
Python не требуется — всё уже внутри образа.

## Полезные команды

```bash
# состояние контейнера и проверка здоровья
docker ps --filter name=quantum-simulator
docker inspect --format="{{.State.Health.Status}}" quantum-simulator

# журнал приложения
docker logs -f quantum-simulator

# остановить и удалить контейнер (образ сохраняется)
docker rm -f quantum-simulator

# запустить заново без пересборки
docker run -d --name quantum-simulator -p 8501:8501 quantum-computer-simulator:1.0.0

# проверить тесты внутри контейнера
docker run --rm quantum-computer-simulator:1.0.0 python -m unittest discover -s tests -t .

# перегенерировать примеры CSV/PNG внутри контейнера
docker run --rm -v "$PWD/examples/results:/app/examples/results" quantum-computer-simulator:1.0.0 python scripts/generate_examples.py
```

## Другой порт

Если 8501 занят, опубликуйте другой порт:

```powershell
docker run -d --name quantum-simulator -p 8600:8501 quantum-computer-simulator:1.0.0
```

Приложение будет доступно по адресу <http://localhost:8600>.

## Если что-то не работает

| Симптом | Что проверить |
|---|---|
| `docker: command not found` | Docker не установлен или не добавлен в PATH; перезапустите терминал. |
| `Cannot connect to the Docker daemon` | Запущен ли Docker Desktop? На Linux — служба `docker`. |
| Сборка падает на `pip install` | Нет доступа к PyPI: подключите интернет или используйте готовый `*.tar`-образ. |
| Страница не открывается | `docker ps` — контейнер запущен? `docker logs quantum-simulator` — нет ли ошибки? Порт 8501 не занят? |
| `port is already allocated` | Запустите с другим портом (`-p 8600:8501`). |
