# Сборка образа и запуск контейнера (Windows PowerShell).
#
# Использование:
#   powershell -ExecutionPolicy Bypass -File docker\build-and-run.ps1
#
# Требуется установленный Docker Desktop (Windows 10/11, WSL2).
# Первая сборка скачивает базовый образ и зависимости — нужен интернет.
# Повторные запуски интернет не требуют.

$ErrorActionPreference = "Stop"

$image = "quantum-computer-simulator:1.0.0"
$container = "quantum-simulator"
$port = 8501
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker не найден. Установите Docker Desktop и повторите запуск." -ForegroundColor Red
    exit 1
}

Push-Location $projectRoot
try {
    Write-Host "Сборка образа $image ..." -ForegroundColor Cyan
    docker build -t $image .
    if ($LASTEXITCODE -ne 0) { throw "Сборка образа завершилась с ошибкой (код $LASTEXITCODE)." }

    $existing = docker ps -a --filter "name=^/$container$" --format "{{.ID}}"
    if ($existing) {
        Write-Host "Удаляю предыдущий контейнер $container ..." -ForegroundColor Cyan
        docker rm -f $container | Out-Null
    }

    Write-Host "Запуск контейнера ..." -ForegroundColor Cyan
    docker run -d --name $container -p "${port}:8501" --restart unless-stopped $image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Не удалось запустить контейнер." }

    Write-Host "Ожидание готовности приложения ..." -ForegroundColor Cyan
    $ready = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_stcore/health" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch {
            # приложение ещё стартует
        }
    }

    if ($ready) {
        Write-Host "Готово. Откройте в браузере: http://localhost:$port" -ForegroundColor Green
        Start-Process "http://localhost:$port"
    } else {
        Write-Host "Контейнер запущен, но приложение ещё не отвечает." -ForegroundColor Yellow
        Write-Host "Проверьте журнал: docker logs $container" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}
