$ErrorActionPreference = 'Stop'

$version = '2026.8.3'
$expectedSha256 = '83E726ED18EA78C5AD5213C4C3A3A27051393950D2BC8ED4DE69BEC12D14EAAE'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $projectRoot 'tools'
$target = Join-Path $toolsDir 'cloudflared.exe'
$download = Join-Path $toolsDir 'cloudflared.download.exe'
$url = "https://github.com/cloudflare/cloudflared/releases/download/$version/cloudflared-windows-amd64.exe"

New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
if (Test-Path -LiteralPath $target) {
    $currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
    if ($currentHash -eq $expectedSha256) {
        Write-Host "Verified cloudflared $version"
        exit 0
    }
}

try {
    Invoke-WebRequest -Uri $url -OutFile $download -UseBasicParsing
    $downloadedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $download).Hash
    if ($downloadedHash -ne $expectedSha256) {
        throw "cloudflared checksum mismatch: expected $expectedSha256, received $downloadedHash"
    }
    Move-Item -LiteralPath $download -Destination $target -Force
    Write-Host "Downloaded and verified cloudflared $version"
}
finally {
    Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
}
