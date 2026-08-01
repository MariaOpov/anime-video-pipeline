[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}

Write-Host "Installing the local FFmpeg runtime..."
& $Python -m pip install -r requirements-phase4.txt
if ($LASTEXITCODE -ne 0) { throw "Phase 4 dependency installation failed with exit code $LASTEXITCODE" }

& $Python -c "import imageio_ffmpeg; print('FFmpeg:', imageio_ffmpeg.get_ffmpeg_version()); print('Executable:', imageio_ffmpeg.get_ffmpeg_exe())"
if ($LASTEXITCODE -ne 0) { throw "FFmpeg verification failed." }

Write-Host "Phase 4 setup complete."
Write-Host "Run: .\run_phase4.ps1"
