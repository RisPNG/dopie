param([switch]$PrepareOnly)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$RuntimeManifest = Get-Content (Join-Path $Root "bootstrap\runtime.json") -Raw | ConvertFrom-Json
$Runtime = Join-Path $env:LOCALAPPDATA "DoPie\runtime"
$Python = Join-Path $Runtime $RuntimeManifest.windows.python
try {
    if (-not (Test-Path $Python)) {
        Write-Host "Downloading and verifying the DoPie runtime..."
        $Staging = Join-Path $Runtime (".setup-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $Staging | Out-Null
        try {
            $Archive = Join-Path $Staging "MsPy.zip"
            Invoke-WebRequest -Uri $RuntimeManifest.windows.url -OutFile $Archive
            if ((Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant() -ne $RuntimeManifest.windows.sha256) {
                throw "MsPy checksum verification failed."
            }
            Expand-Archive -Path $Archive -DestinationPath $Staging -Force
            $RuntimeFolder = ($RuntimeManifest.windows.python -split "/")[0]
            try {
                [System.IO.Directory]::Move((Join-Path $Staging $RuntimeFolder), (Join-Path $Runtime $RuntimeFolder))
            } catch {
                if (-not (Test-Path $Python)) {
                    throw
                }
            }
        } finally {
            Remove-Item -Recurse -Force $Staging -ErrorAction SilentlyContinue
        }
    }
    $Bootstrap = Join-Path $Root "bootstrap\bootstrap.py"
    if ($PrepareOnly) {
        Write-Host "Preparing the DoPie application environment..."
        & $Python $Bootstrap --prepare-only
        if ($LASTEXITCODE -ne 0) {
            throw "Preparing the DoPie application environment failed with exit code $LASTEXITCODE."
        }
        Write-Host "Setup complete. Starting DoPie..."
    } else {
        & $Python $Bootstrap
    }
} catch {
    if ($PrepareOnly) {
        Write-Host $_
        Read-Host "DoPie setup failed. Press Enter to close"
    }
    throw
}
exit $LASTEXITCODE
