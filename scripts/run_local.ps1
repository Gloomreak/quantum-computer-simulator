# Локальный запуск без Docker (Windows PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
#
# Если окружение .venv уже создано и зависимости установлены, скрипт сразу
# запускает приложение и не обращается в интернет. Иначе создаёт .venv и
# устанавливает зависимости (нужен интернет один раз).

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host "Python не найден. Установите Python 3.11+ (python.org) и повторите." -ForegroundColor Red
        exit 1
    }

    $venvPython = ".venv\Scripts\python.exe"
    $hasStreamlit = $false
    if (Test-Path $venvPython) {
        & $venvPython -c "import streamlit" 2>$null
        $hasStreamlit = ($LASTEXITCODE -eq 0)
    }

    if (-not $hasStreamlit) {
        if (-not (Test-Path $venvPython)) {
            Write-Host "Создаю виртуальное окружение .venv ..." -ForegroundColor Cyan
            python -m venv .venv
        }
        Write-Host "Устанавливаю зависимости (нужен интернет) ..." -ForegroundColor Cyan
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r requirements.txt
    } else {
        Write-Host "Окружение готово, установка зависимостей не требуется." -ForegroundColor Green
    }

    Write-Host "Запуск приложения: http://localhost:8501" -ForegroundColor Green
    & $venvPython -m streamlit run app.py
} finally {
    Pop-Location
}
