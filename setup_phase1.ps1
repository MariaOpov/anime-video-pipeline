[CmdletBinding()]
param(
    [string]$PythonCommand = "py",
    [string]$VenvDirectory = ".venv"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command $PythonCommand -ErrorAction SilentlyContinue)) {
    throw "Python launcher '$PythonCommand' was not found. Install Python 3.10+ first."
}

if ($PythonCommand -eq "py") {
    & $PythonCommand -3 -m venv $VenvDirectory
} else {
    & $PythonCommand -m venv $VenvDirectory
}

$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt
& $VenvPython -m unittest discover -s tests -v

Write-Host "Phase 1 setup complete."
Write-Host "Run: $VenvPython run_pipeline.py --project projects/demo --dry-run"
