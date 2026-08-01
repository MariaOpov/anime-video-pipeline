[CmdletBinding()]
param(
    [string]$Project = "projects\demo"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}

& $Python finish_phase4.py --project $Project --dry-run
if ($LASTEXITCODE -ne 0) { throw "Phase 4 preflight failed with exit code $LASTEXITCODE" }

& $Python finish_phase4.py --project $Project
if ($LASTEXITCODE -ne 0) { throw "Phase 4 export failed with exit code $LASTEXITCODE" }

$ProjectPath = (Resolve-Path $Project).Path
$Report = Join-Path $ProjectPath "generated\phase4_report.json"
if (-not (Test-Path $Report -PathType Leaf)) {
    throw "Phase 4 finished without creating: $Report"
}
$ReportData = Get-Content $Report -Raw | ConvertFrom-Json
$OutputVideo = Join-Path $ProjectPath $ReportData.output_video
if (-not (Test-Path $OutputVideo -PathType Leaf)) {
    throw "Phase 4 finished without creating: $OutputVideo"
}

Write-Host "Phase 4 complete. Final video: $OutputVideo"
