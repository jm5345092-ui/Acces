# Script PowerShell - Configura .env y obtiene IP de WSL

Write-Host "================================"
Write-Host "Configurando ACCES en Windows"
Write-Host "================================"
Write-Host ""

# Obtener IP de WSL
Write-Host "Obteniendo IP de WSL..."
$wslIp = wsl hostname -I | Out-String | ForEach-Object { $_.Trim().Split()[0] }

if ([string]::IsNullOrEmpty($wslIp)) {
    Write-Host "ERROR: No se pudo obtener IP de WSL"
    Write-Host "Asegúrate que WSL está corriendo"
    exit 1
}

Write-Host "IP de WSL: $wslIp"
Write-Host ""

# Configurar .env
$envPath = "C:\xampp\htdocs\ACCES\portal\.env"

Write-Host "Creando $envPath..."

$envContent = @"
NODE_ENV=development
PORT=3000

DATABASE_URL=postgresql://acces:acces@$wslIp:5432/acces

SERVICE_KEY=desarrollo-local-secret
PORTAL_BASE_URL=http://localhost:3000
# URL pública por la que se conectan los APKs compilados (túnel ngrok u otro dominio público).
WEBSOCKET_URL=ws://localhost:3000

METERED_API_KEY=
"@

Set-Content -Path $envPath -Value $envContent -Encoding UTF8

Write-Host ".env creado:"
Get-Content $envPath
Write-Host ""

Write-Host "================================"
Write-Host "Setup completado"
Write-Host "================================"
Write-Host ""
Write-Host "Ahora ejecuta en PowerShell:"
Write-Host "  cd C:\xampp\htdocs\ACCES\portal"
Write-Host "  npm start"
Write-Host ""
Write-Host "En otra terminal:"
Write-Host "  node worker.js"
Write-Host ""
