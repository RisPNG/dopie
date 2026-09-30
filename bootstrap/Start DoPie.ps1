param([switch]$PrepareOnly)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$RuntimeManifest = Get-Content (Join-Path $Root "bootstrap\runtime.json") -Raw | ConvertFrom-Json
$Runtime = Join-Path $Root "runtime\windows"
$Python = Join-Path $Runtime $RuntimeManifest.windows.python
if (-not (Test-Path $Python)) {
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
    & $Python $Bootstrap --prepare-only
} else {
    & $Python $Bootstrap
}
exit $LASTEXITCODE
