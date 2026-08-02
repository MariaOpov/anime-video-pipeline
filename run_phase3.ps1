[CmdletBinding()]
param(
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$Project = "projects\demo",
    [switch]$Render,
    [switch]$SkipPhase2
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}
if (-not (Test-Path $Blender -PathType Leaf)) {
    throw "Blender executable not found: $Blender"
}

if (-not $SkipPhase2) {
    Write-Host "Refreshing Phase 2 outputs..."
    & $Python run_pipeline.py --project $Project --phase 2 --preset preview --resume
    if ($LASTEXITCODE -ne 0) { throw "Phase 2 refresh failed with exit code $LASTEXITCODE" }
}

Write-Host "Preparing validated Phase 3 manifest..."
& $Python prepare_phase3.py --project $Project
if ($LASTEXITCODE -ne 0) { throw "Phase 3 manifest failed with exit code $LASTEXITCODE" }

$ProjectPath = (Resolve-Path $Project).Path
$ManifestPath = Join-Path $ProjectPath "generated\phase3_manifest.json"
$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$BaseScene = Join-Path $ProjectPath $Manifest.base_scene
$OutputScene = Join-Path $ProjectPath $Manifest.output_scene
$PreviewVideo = Join-Path $ProjectPath $Manifest.preview_video

if (-not (Test-Path $BaseScene -PathType Leaf)) {
    throw "Base Blender scene not found: $BaseScene. Run run_step2.ps1 first."
}

$BlenderArguments = @(
    "--background", $BaseScene,
    "--python", "blender_scripts\build_phase3_scene.py",
    "--", "--project", $ProjectPath
)
if ($Render) { $BlenderArguments += "--render" }

& $Blender @BlenderArguments
if ($LASTEXITCODE -ne 0) { throw "Blender Phase 3 assembly failed with exit code $LASTEXITCODE" }
if (-not (Test-Path $OutputScene -PathType Leaf)) {
    throw "Blender finished without creating: $OutputScene"
}
if ($Render -and (-not (Test-Path $PreviewVideo -PathType Leaf))) {
    throw "Blender finished without rendering: $PreviewVideo"
}
$Phase8Report = Join-Path $ProjectPath $Manifest.harmonization.report
if ($Manifest.harmonization.enabled -and (-not (Test-Path $Phase8Report -PathType Leaf))) {
    throw "Blender finished without the Phase 8 audit: $Phase8Report"
}
if ($Manifest.harmonization.enabled) {
    & $Python verify_phase8.py --project $ProjectPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 8 schema/readiness verification failed" }
}

Write-Host "Phase 3 complete. Scene: $OutputScene"
if ($Manifest.harmonization.enabled) { Write-Host "Phase 8 audit: $Phase8Report" }
if ($Render) { Write-Host "Preview: $PreviewVideo" }
