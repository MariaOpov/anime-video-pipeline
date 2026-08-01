[CmdletBinding()]
param(
    [string]$Voice = "vi_VN-vais1000-medium"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python environment is missing. Run setup_phase1.ps1 first."
}

Write-Host "Installing Piper TTS..."
& $Python -m pip install -r requirements-phase2.txt
if ($LASTEXITCODE -ne 0) { throw "Piper installation failed with exit code $LASTEXITCODE" }

$VoiceDirectory = Join-Path $PSScriptRoot "tools\piper_voices"
New-Item -ItemType Directory -Force -Path $VoiceDirectory | Out-Null
Write-Host "Downloading Piper voice: $Voice"
& $Python -m piper.download_voices --data-dir $VoiceDirectory $Voice
if ($LASTEXITCODE -ne 0) { throw "Piper voice download failed with exit code $LASTEXITCODE" }

$RhubarbDirectory = Join-Path $PSScriptRoot "tools\rhubarb"
$RhubarbExe = Join-Path $RhubarbDirectory "rhubarb.exe"
$RhubarbResource = Join-Path $RhubarbDirectory "res\sphinx\cmudict-en-us.dict"
if ((-not (Test-Path $RhubarbExe -PathType Leaf)) -or
    (-not (Test-Path $RhubarbResource -PathType Leaf))) {
    Write-Host "Downloading Rhubarb Lip Sync..."
    $Release = Invoke-RestMethod `
        -Uri "https://api.github.com/repos/DanielSWolf/rhubarb-lip-sync/releases/latest" `
        -Headers @{ "User-Agent" = "anime-video-pipeline" }
    $Asset = $Release.assets |
        Where-Object { $_.name -match "Windows.*\.zip$" } |
        Select-Object -First 1
    if (-not $Asset) { throw "The latest Rhubarb release has no Windows ZIP asset." }

    $TempDirectory = Join-Path $env:TEMP ("anime-pipeline-rhubarb-" + [guid]::NewGuid())
    $Archive = Join-Path $TempDirectory "rhubarb.zip"
    $Extracted = Join-Path $TempDirectory "extracted"
    try {
        New-Item -ItemType Directory -Force -Path $TempDirectory, $Extracted | Out-Null
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $Archive
        Expand-Archive -Path $Archive -DestinationPath $Extracted -Force
        $DownloadedExe = Get-ChildItem $Extracted -Recurse -File -Filter "rhubarb.exe" |
            Select-Object -First 1
        if (-not $DownloadedExe) { throw "rhubarb.exe was not found inside the downloaded archive." }
        New-Item -ItemType Directory -Force -Path $RhubarbDirectory | Out-Null
        Copy-Item `
            -Path (Join-Path $DownloadedExe.Directory.FullName "*") `
            -Destination $RhubarbDirectory `
            -Recurse `
            -Force
    }
    finally {
        if (Test-Path $TempDirectory) {
            Remove-Item $TempDirectory -Recurse -Force
        }
    }
}

if (-not (Test-Path $RhubarbResource -PathType Leaf)) {
    throw "Rhubarb resource installation is incomplete: $RhubarbResource"
}

& $Python -m piper --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Piper verification failed." }
& $RhubarbExe --version
if ($LASTEXITCODE -ne 0) { throw "Rhubarb verification failed." }

Write-Host "Phase 2 setup complete."
Write-Host "Run: $Python run_pipeline.py --project projects/demo --phase 2 --dry-run"
