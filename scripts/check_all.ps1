# Полная проверка проекта (Windows PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\check_all.ps1
#
# Выполняет: проверку синтаксиса всех модулей, автоматические тесты и
# проверку отрисовки страниц интерфейса (без установленного Streamlit).

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $python = ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }

    Write-Host "1/3 Проверка синтаксиса ..." -ForegroundColor Cyan
    & $python -m compileall -q app.py src tests scripts tools
    if ($LASTEXITCODE -ne 0) { throw "Ошибка компиляции." }

    Write-Host "2/3 Автоматические тесты ..." -ForegroundColor Cyan
    & $python -m unittest discover -s tests -t .
    if ($LASTEXITCODE -ne 0) { throw "Тесты не прошли." }

    Write-Host "3/3 Проверка страниц интерфейса ..." -ForegroundColor Cyan
    & $python tools/ui_check.py
    if ($LASTEXITCODE -ne 0) { throw "Проверка интерфейса не прошла." }

    Write-Host "Все проверки пройдены." -ForegroundColor Green
} finally {
    Pop-Location
}
