[CmdletBinding()]
param(
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$Project = "projects\demo",
    [ValidateSet("preview", "balanced", "final")]
    [string]$Preset = "preview",
    [switch]$Render,
    [switch]$Fresh,
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Render) {
    throw "Phase 5 requires explicit render approval. Run: .\run_all.ps1 -Render"
}

if ($Setup) {
    & ".\setup_phase1.ps1"
    if ($LASTEXITCODE -ne 0) { throw "Phase 1 setup failed with exit code $LASTEXITCODE" }
    & ".\setup_phase2.ps1"
    if ($LASTEXITCODE -ne 0) { throw "Phase 2 setup failed with exit code $LASTEXITCODE" }
    & ".\setup_phase4.ps1"
    if ($LASTEXITCODE -ne 0) { throw "Phase 4 setup failed with exit code $LASTEXITCODE" }
}

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run .\run_all.ps1 -Render -Setup"
}
if (-not (Test-Path $Blender -PathType Leaf)) {
    throw "Blender executable not found: $Blender"
}
if (-not (Test-Path $Project -PathType Container)) {
    throw "Project directory not found: $Project"
}

$ProjectPath = (Resolve-Path $Project).Path
$GeneratedDirectory = Join-Path $ProjectPath "generated"
New-Item -ItemType Directory -Force -Path $GeneratedDirectory | Out-Null
$RunRecord = Join-Path $GeneratedDirectory "phase5_run_record.json"
$StartedAt = [DateTimeOffset]::UtcNow
$StageResults = [ordered]@{}

function Write-RunRecord {
    param([string]$Status)
    $Record = [ordered]@{
        status = $Status
        started_at = $StartedAt.ToString("o")
        completed_at = if ($Status -eq "running") { $null } else { [DateTimeOffset]::UtcNow.ToString("o") }
        preset = $Preset
        render = [bool]$Render
        resume = -not [bool]$Fresh
        stages = @($StageResults.Values)
    }
    $Json = $Record | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($RunRecord, $Json, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-PipelineStage {
    param(
        [string]$Name,
        [int]$Phase,
        [scriptblock]$Action
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $Action
        $Stopwatch.Stop()
        $StageResults[$Name] = [ordered]@{
            name = $Name
            phase = $Phase
            status = "complete"
            duration_seconds = [Math]::Round($Stopwatch.Elapsed.TotalSeconds, 3)
        }
        Write-RunRecord "running"
    }
    catch {
        $Stopwatch.Stop()
        $StageResults[$Name] = [ordered]@{
            name = $Name
            phase = $Phase
            status = "failed"
            duration_seconds = [Math]::Round($Stopwatch.Elapsed.TotalSeconds, 3)
            error = $_.Exception.Message
        }
        Write-RunRecord "failed"
        throw
    }
}

Write-RunRecord "running"

Invoke-PipelineStage "preflight" 0 {
    & $Python -c "import piper, imageio_ffmpeg; print('Python dependencies ready'); print('FFmpeg:', imageio_ffmpeg.get_ffmpeg_version())"
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 2/4 dependencies are missing. Run .\run_all.ps1 -Render -Setup"
    }
    $BlenderVersionOutput = & $Blender --version
    if ($LASTEXITCODE -ne 0) { throw "Blender preflight failed with exit code $LASTEXITCODE" }
    $VersionLine = $BlenderVersionOutput | Select-Object -First 1
    Write-Host $VersionLine
    & $Python "run_pipeline.py" --project $ProjectPath --phase 2 --preset $Preset --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Pipeline preflight failed with exit code $LASTEXITCODE" }
}

Invoke-PipelineStage "phase1_phase2" 2 {
    $Arguments = @("run_pipeline.py", "--project", $ProjectPath, "--phase", "2", "--preset", $Preset)
    if (-not $Fresh) { $Arguments += "--resume" }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Phase 1/2 failed with exit code $LASTEXITCODE" }
}

Invoke-PipelineStage "phase3_blender_phase8_harmonization" 8 {
    & ".\run_phase3.ps1" -Blender $Blender -Project $ProjectPath -Render -SkipPhase2
    if ($LASTEXITCODE -ne 0) { throw "Phase 3 failed with exit code $LASTEXITCODE" }
}

Invoke-PipelineStage "phase4_finishing" 4 {
    & ".\run_phase4.ps1" -Project $ProjectPath
    if ($LASTEXITCODE -ne 0) { throw "Phase 4 failed with exit code $LASTEXITCODE" }
}

Write-RunRecord "complete"
& $Python "finalize_phase5.py" --project $ProjectPath --blender $Blender --run-record $RunRecord
if ($LASTEXITCODE -ne 0) {
    Write-RunRecord "failed"
    throw "Phase 5 quality audit failed with exit code $LASTEXITCODE"
}

$ProductionReport = Join-Path $ProjectPath "generated\production_report.json"
$ProductionData = Get-Content $ProductionReport -Raw -Encoding UTF8 | ConvertFrom-Json
$FinalArtifact = $ProductionData.artifacts | Where-Object { $_.name -eq "final_video" } | Select-Object -First 1
$FinalVideo = Join-Path $ProjectPath $FinalArtifact.path
Write-Host "`nPRODUCTION PIPELINE THROUGH PHASE 8 COMPLETE" -ForegroundColor Green
Write-Host "Final video: $FinalVideo"
Write-Host "Production report: $ProductionReport"
