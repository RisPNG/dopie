$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RuntimeManifest = Get-Content (Join-Path $Root "bootstrap\runtime.json") -Raw | ConvertFrom-Json
$Python = Join-Path (Join-Path $Root "runtime\windows") $RuntimeManifest.windows.python
$Archive = Join-Path $Root "runtime\windows\MsPy.zip"
if (-not (Test-Path $Python)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Archive) | Out-Null
    Invoke-WebRequest -Uri $RuntimeManifest.windows.url -OutFile $Archive
    if ((Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant() -ne $RuntimeManifest.windows.sha256) {
        throw "MsPy checksum verification failed."
    }
    Expand-Archive -Path $Archive -DestinationPath (Split-Path -Parent $Archive) -Force
    Remove-Item $Archive
}
& $Python (Join-Path $Root "bootstrap\bootstrap.py")
exit $LASTEXITCODE
