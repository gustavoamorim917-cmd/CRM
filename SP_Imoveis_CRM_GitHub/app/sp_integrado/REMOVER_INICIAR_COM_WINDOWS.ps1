$taskName = "SP Imoveis CRM WhatsApp"
$removed = $false

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host "Inicializacao automatica removida." -ForegroundColor Green
    $removed = $true
} catch {
}

$startup = [Environment]::GetFolderPath("Startup")
$vbsPath = Join-Path $startup "SP Imoveis CRM WhatsApp.vbs"
if (Test-Path -LiteralPath $vbsPath) {
    Remove-Item -LiteralPath $vbsPath -Force
    Write-Host "Inicializador da pasta Inicializar removido." -ForegroundColor Green
    $removed = $true
}

if (-not $removed) {
    Write-Host "Nenhuma inicializacao automatica encontrada para remover." -ForegroundColor Yellow
}
