[CmdletBinding()]
param(
    [string]$Project = "projects\demo",
    [string]$Blender = "D:\Blender_5.1\blender.exe",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}
if (-not (Test-Path $Project -PathType Container)) {
    throw "Project directory not found: $Project"
}
if ($HostAddress -notin @("127.0.0.1", "localhost")) {
    throw "Studio only permits a local loopback host."
}

$env:ANIME_PIPELINE_PROJECT = (Resolve-Path $Project).Path
$env:ANIME_PIPELINE_BLENDER = $Blender
$Url = "http://${HostAddress}:$Port"

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($StudioUrl)
        Start-Sleep -Milliseconds 1200
        Start-Process $StudioUrl
    } -ArgumentList $Url | Out-Null
}

Write-Host "Anime Pipeline Studio: $Url"
Write-Host "Press Ctrl+C to stop the local server."
& $Python -m uvicorn studio_app:app --host $HostAddress --port $Port
if ($LASTEXITCODE -ne 0) { throw "Studio stopped with exit code $LASTEXITCODE" }
