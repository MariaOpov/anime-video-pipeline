[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Character,
    [Parameter(Mandatory = $true)]
    [string]$Model,
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$Project = "projects\demo",
    [string]$Creator = "Unknown",
    [string]$Source = "Unknown",
    [string]$LicenseName = "Unknown"
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
if (-not (Test-Path $Model -PathType Leaf)) {
    throw "MMD model not found: $Model"
}

$ProjectPath = (Resolve-Path $Project).Path
$Request = Join-Path $ProjectPath "generated\phase7_import_request.json"

& $Python prepare_phase7.py `
    --project $ProjectPath `
    --character $Character `
    --model $Model `
    --request $Request `
    --creator $Creator `
    --source $Source `
    --license-name $LicenseName
if ($LASTEXITCODE -ne 0) { throw "Phase 7 request preparation failed with exit code $LASTEXITCODE" }

& $Blender `
    --background `
    --python "blender_scripts\onboard_mmd_character.py" `
    -- `
    --request $Request
if ($LASTEXITCODE -ne 0) { throw "Phase 7 Blender onboarding failed with exit code $LASTEXITCODE" }

& $Python finalize_phase7.py --project $ProjectPath --request $Request
if ($LASTEXITCODE -ne 0) { throw "Phase 7 profile validation failed with exit code $LASTEXITCODE" }

Write-Host "Phase 7 complete. Character '$Character' is ready for the next Phase 3 build."
