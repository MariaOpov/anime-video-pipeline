[CmdletBinding()]
param(
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$Project = "projects\demo"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path $Blender -PathType Leaf)) {
    throw "Blender executable not found: $Blender"
}
if (-not (Test-Path ".venv\Scripts\python.exe" -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}

& $Blender --background --python "blender_scripts\create_demo_assets.py" -- --project $Project
if ($LASTEXITCODE -ne 0) { throw "Blender demo-asset generation failed with exit code $LASTEXITCODE" }

$ExpectedOutputs = @(
    "$Project\assets\characters\demo_characters.blend",
    "$Project\assets\motions\demo_motions.blend",
    "$Project\blender_scenes\demo_mannequins.blend"
)

$MissingOutputs = $ExpectedOutputs |
    Where-Object { -not (Test-Path $_ -PathType Leaf) }

if ($MissingOutputs.Count -gt 0) {
    throw "Blender finished without creating: $($MissingOutputs -join ', ')"
}

& ".venv\Scripts\python.exe" run_pipeline.py --project $Project --preset preview
if ($LASTEXITCODE -ne 0) { throw "Phase 1 refresh failed with exit code $LASTEXITCODE" }

Write-Host "Step 2 complete. Open: $Project\blender_scenes\demo_mannequins.blend"

