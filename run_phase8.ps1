[CmdletBinding()]
param(
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$Project = "projects\demo",
    [switch]$Render
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = ".venv\Scripts\python.exe"

& ".\run_phase3.ps1" -Blender $Blender -Project $Project -SkipPhase2 -Render:$Render
if ($LASTEXITCODE -ne 0) {
    throw "Phase 8 harmonization failed with exit code $LASTEXITCODE"
}

$ProjectPath = (Resolve-Path $Project).Path
$ManifestPath = Join-Path $ProjectPath "generated\phase3_manifest.json"
$Manifest = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ReportPath = Join-Path $ProjectPath $Manifest.harmonization.report
if (-not (Test-Path $ReportPath -PathType Leaf)) {
    throw "Phase 8 report is missing: $ReportPath"
}
$Report = Get-Content $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
& $Python "verify_phase8.py" --project $ProjectPath
if ($LASTEXITCODE -ne 0) { throw "Phase 8 schema/readiness verification failed" }

Write-Host (
    "PHASE 8 COMPLETE - {0}/{1} character(s), {2}/{3} shot(s) framed. Report: {4}" -f `
    $Report.summary.ready_character_count, $Report.summary.character_count, `
    $Report.summary.framing_passed_shot_count, $Report.summary.adaptive_camera_shot_count, `
    $ReportPath
) -ForegroundColor Green
