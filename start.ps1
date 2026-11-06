$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$trainingPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $trainingPython) {
    & $trainingPython server.py --host 127.0.0.1 --port 55290
} else {
    python server.py --host 127.0.0.1 --port 55290
}
