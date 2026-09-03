$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
npm run build:desktop
Copy-Item 'desktop-dist\desktop\index.html' 'desktop-dist\index.html' -Force
py -3.12 backend\models\download_models.py
py -3.12 desktop\package_source.py
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name IDShield-AI-Windows `
  --collect-all rapidocr_onnxruntime `
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on `
  --add-data "desktop-dist;desktop-dist" --add-data "backend\models;backend\models" `
  --add-binary "tools\cloudflared.exe;." desktop\launcher.py
Write-Host "Built: $root\dist\IDShield-AI-Windows.exe"
Write-Host "Source: $root\dist\IDShield-AI-source.zip"
