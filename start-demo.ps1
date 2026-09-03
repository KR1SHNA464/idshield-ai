$ErrorActionPreference = 'Stop'
docker compose up --build -d
$port = 8080
try {
    $probe = [System.Net.Sockets.UdpClient]::new()
    $probe.Connect('8.8.8.8', 80)
    $lanIp = $probe.Client.LocalEndPoint.Address.ToString()
    $probe.Dispose()
} catch { $lanIp = 'YOUR-LAN-IP' }
Write-Host "IDShield AI is ready: http://localhost:$port"
Write-Host "Same Wi-Fi link: http://${lanIp}:$port"
$bundled = Join-Path $PSScriptRoot 'tools\cloudflared.exe'
$installed = Get-Command cloudflared -ErrorAction SilentlyContinue
$tunnel = if (Test-Path $bundled) { $bundled } elseif ($installed) { $installed.Source } else { $null }
if ($tunnel) {
    Write-Host 'Starting a temporary public HTTPS link. Press Ctrl+C to stop.'
    try { & $tunnel tunnel --url "http://127.0.0.1:$port" --no-autoupdate --protocol http2 }
    finally { docker compose down }
} else {
    Write-Host 'Optional public link: install cloudflared, then run: cloudflared tunnel --url http://127.0.0.1:8080'
    Write-Host 'Run "docker compose down" when the demo is finished.'
}
