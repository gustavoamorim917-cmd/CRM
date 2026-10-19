param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot

function Get-EnvValue([string]$Path, [string]$Key) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

$envPath = Join-Path $AppDir ".env"
$configuredDataDir = Get-EnvValue $envPath "CRM_DATA_DIR"
if ($configuredDataDir) {
    $configuredDataDir = [Environment]::ExpandEnvironmentVariables($configuredDataDir)
    $DataDir = $configuredDataDir
} else {
    $DataDir = Join-Path $AppDir "data"
}

if (-not (Test-Path -LiteralPath $DataDir)) {
    throw "Pasta de dados nao encontrada: $DataDir"
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $DataDir "backups"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $OutputDir "dados_crm_$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$dbPath = Join-Path $DataDir "crm.sqlite3"
if (Test-Path -LiteralPath $dbPath) {
    Copy-Item -LiteralPath $dbPath -Destination $backupDir -Force
}

$uploadsPath = Join-Path $DataDir "uploads"
if (Test-Path -LiteralPath $uploadsPath) {
    Copy-Item -LiteralPath $uploadsPath -Destination $backupDir -Recurse -Force
}

if (Test-Path -LiteralPath $envPath) {
    Copy-Item -LiteralPath $envPath -Destination (Join-Path $backupDir ".env") -Force
}

$zipPath = "$backupDir.zip"
Compress-Archive -LiteralPath $backupDir -DestinationPath $zipPath -Force

Write-Host "Backup criado:" -ForegroundColor Green
Write-Host $zipPath
