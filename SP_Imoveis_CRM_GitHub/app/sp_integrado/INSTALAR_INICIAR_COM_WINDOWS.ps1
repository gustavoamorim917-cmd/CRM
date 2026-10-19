$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$taskName = "SP Imoveis CRM WhatsApp"
$scriptPath = Join-Path $PSScriptRoot "INICIAR_APP.ps1"

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "INICIAR_APP.ps1 nao encontrado. Extraia o ZIP antes de instalar."
}

$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -NoBrowser -FixedPort -PreferredPort 5002"

$startup = [Environment]::GetFolderPath("Startup")
$vbsPath = Join-Path $startup "$taskName.vbs"
$psEscaped = $scriptPath.Replace('"', '""')
$command = "$powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$psEscaped"" -NoBrowser -FixedPort -PreferredPort 5002"
$vbsCommand = $command.Replace('"', '""')
$vbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "$vbsCommand", 0, False
"@
Set-Content -LiteralPath $vbsPath -Value $vbs -Encoding ASCII
Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""

$url = "http://127.0.0.1:5002"
Write-Host ""
Write-Host "Inicializacao automatica instalada na pasta Inicializar do Windows." -ForegroundColor Green
Write-Host "A partir do proximo login, o app vai iniciar sozinho na porta 5002." -ForegroundColor Green
Write-Host "Abrindo $url ..." -ForegroundColor Cyan

for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -Uri "$url/api/health" -TimeoutSec 1 -UseBasicParsing *> $null
        Start-Process $url
        exit 0
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host "A tarefa foi criada, mas o app ainda nao respondeu. Reinicie o Windows ou execute INICIAR_APP.bat." -ForegroundColor Yellow
