$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$dbPath = Join-Path $PSScriptRoot "data\crm.sqlite3"
if (-not (Test-Path -LiteralPath $dbPath)) {
    throw "Banco nao encontrado em $dbPath"
}

$backupDir = Join-Path $PSScriptRoot "data\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $backupDir "crm_backup_$stamp.sqlite3"
Copy-Item -LiteralPath $dbPath -Destination $backupPath -Force

Write-Host "Backup do banco salvo em:" -ForegroundColor Green
Write-Host $backupPath -ForegroundColor Cyan
