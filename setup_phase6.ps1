[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}

Write-Host "Installing Anime Pipeline Studio..."
& $Python -m pip install -r requirements-phase6.txt
if ($LASTEXITCODE -ne 0) { throw "Phase 6 dependency installation failed with exit code $LASTEXITCODE" }

& $Python -c "import fastapi, uvicorn; print('FastAPI:', fastapi.__version__); print('Uvicorn:', uvicorn.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Phase 6 verification failed." }

Write-Host "Phase 6 setup complete."
Write-Host "Run: .\run_studio.ps1"
