# Сохранить готовый образ в файл для переноса на другой компьютер.
#
# Использование:
#   powershell -ExecutionPolicy Bypass -File docker\export-image.ps1
#
# Результат: dist\quantum-simulator-image.tar
# Файл можно скопировать на ноутбук с Docker и загрузить командой
#   docker load -i quantum-simulator-image.tar
# (см. docker\load-and-run.ps1). Python и библиотеки на той машине не нужны.

$ErrorActionPreference = "Stop"

$image = "quantum-computer-simulator:1.0.0"
$projectRoot = Split-Path -Parent $PSScriptRoot
$distDir = Join-Path $projectRoot "dist"
$target = Join-Path $distDir "quantum-simulator-image.tar"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker не найден." -ForegroundColor Red
    exit 1
}

$images = docker images --format "{{.Repository}}:{{.Tag}}" |
    Where-Object { $_ -eq $image }
if (-not $images) {
    Write-Host "Образ $image не найден. Сначала выполните docker\build-and-run.ps1." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
Write-Host "Сохраняю образ в $target ..." -ForegroundColor Cyan
docker save -o $target $image
if ($LASTEXITCODE -ne 0) { throw "Не удалось сохранить образ." }

$sizeMb = [math]::Round((Get-Item $target).Length / 1MB, 1)
Write-Host "Готово: $target ($sizeMb МБ)" -ForegroundColor Green
Write-Host "Скопируйте файл вместе с папкой docker на целевой компьютер." -ForegroundColor Green
