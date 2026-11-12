# Запуск построения 3D-модели корпуса редуктора в КОМПАС-3D v24.
# Использование (из папки проекта):
#   powershell -ExecutionPolicy Bypass -File .\run_kompas.ps1
#   powershell -ExecutionPolicy Bypass -File .\run_kompas.ps1 -Output "D:\models\korpus.m3d"
param(
    [string]$Output = "",
    [string]$KompasDir = "C:\Program Files\ASCON\KOMPAS-3D v24"
)

$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# 1. Python
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $pyExe = "py"; $pyPre = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyExe = "python"; $pyPre = @() }
else { throw "Python 3 не найден. Установите с https://www.python.org (галочка 'Add to PATH')." }

# 2. Виртуальное окружение + pywin32
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "Создаю .venv ..."
    & $pyExe @pyPre -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install --disable-pip-version-check -q -r requirements.txt

# 3. Регистрация COM-сервера КОМПАС (нужна для API)
if (-not (Test-Path "Registry::HKEY_CLASSES_ROOT\Kompas.Application.5")) {
    $exe = Join-Path $KompasDir "Bin\kOMPAS.exe"
    if (-not (Test-Path $exe)) {
        throw "КОМПАС не зарегистрирован в COM и не найден в '$KompasDir'. Укажите -KompasDir."
    }
    Write-Host "Регистрирую COM-сервер КОМПАС (потребуются права администратора)..."
    Start-Process -FilePath $exe -ArgumentList "/regserver" -Verb RunAs -Wait
}

# 4. Построение
$pyArgs = @("build_korpus.py")
if ($Output) { $pyArgs += @("--output", $Output) }
python @pyArgs
