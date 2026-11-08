# Загрузить образ из файла и запустить контейнер (Windows PowerShell).
#
# Использование:
#   powershell -ExecutionPolicy Bypass -File docker\load-and-run.ps1 -Archive dist\quantum-simulator-image.tar
#
# Нужен только Docker: ни Python, ни pip, ни интернет не требуются.

param(
    [string]$Archive = "",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"

$image = "quantum-computer-simulator:1.0.0"
$container = "quantum-simulator"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Archive)) {
    $Archive = Join-Path $projectRoot "dist\quantum-simulator-image.tar"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker не найден. Установите Docker Desktop." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Archive)) {
    Write-Host "Файл образа не найден: $Archive" -ForegroundColor Red
    exit 1
}

Write-Host "Загружаю образ из $Archive ..." -ForegroundColor Cyan
docker load -i $Archive
if ($LASTEXITCODE -ne 0) { throw "Не удалось загрузить образ." }

$existing = docker ps -a --filter "name=^/$container$" --format "{{.ID}}"
if ($existing) {
    docker rm -f $container | Out-Null
}

Write-Host "Запуск контейнера ..." -ForegroundColor Cyan
docker run -d --name $container -p "${Port}:8501" --restart unless-stopped $image | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Не удалось запустить контейнер." }

Write-Host "Готово. Откройте в браузере: http://localhost:$Port" -ForegroundColor Green
Start-Process "http://localhost:$Port"
