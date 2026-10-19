param(
    [string]$TargetAppPath = "",
    [switch]$StopRunning
)

$ErrorActionPreference = "Stop"
$SourceAppPath = $PSScriptRoot

if (-not $TargetAppPath) {
    $TargetAppPath = $SourceAppPath
}

$SourceAppPath = (Resolve-Path -LiteralPath $SourceAppPath).Path
$TargetAppPath = (Resolve-Path -LiteralPath $TargetAppPath).Path
$SamePath = $SourceAppPath.TrimEnd("\") -ieq $TargetAppPath.TrimEnd("\")

if (-not (Test-Path -LiteralPath (Join-Path $SourceAppPath "app.py"))) {
    throw "Fonte invalida: app.py nao encontrado em $SourceAppPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $TargetAppPath "app.py"))) {
    throw "Destino invalido: app.py nao encontrado em $TargetAppPath"
}

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

function Resolve-DataDir([string]$AppPath) {
    $envPath = Join-Path $AppPath ".env"
    $configured = Get-EnvValue $envPath "CRM_DATA_DIR"
    if ($configured) {
        return [Environment]::ExpandEnvironmentVariables($configured)
    }
    return Join-Path $AppPath "data"
}

function Stop-TargetApp([string]$AppPath) {
    $needle = (Join-Path $AppPath "app.py").ToLowerInvariant()
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($needle)
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Servidor encerrado. PID: $($process.ProcessId)" -ForegroundColor Yellow
    }
}

if ($StopRunning) {
    Stop-TargetApp $TargetAppPath
}

$DataDir = Resolve-DataDir $TargetAppPath
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "backups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "uploads") | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $DataDir "backups\updates\antes_update_$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$targetDb = Join-Path $DataDir "crm.sqlite3"
if (Test-Path -LiteralPath $targetDb) {
    Copy-Item -LiteralPath $targetDb -Destination $backupDir -Force
}

$targetUploads = Join-Path $DataDir "uploads"
if (Test-Path -LiteralPath $targetUploads) {
    Copy-Item -LiteralPath $targetUploads -Destination $backupDir -Recurse -Force
}

$targetEnv = Join-Path $TargetAppPath ".env"
if (Test-Path -LiteralPath $targetEnv) {
    Copy-Item -LiteralPath $targetEnv -Destination (Join-Path $backupDir ".env") -Force
}

$files = @(
    "app.py",
    "requirements.txt",
    "README.md",
    "INTEGRACAO_N8N.md",
    "INSTALAR_OUTRO_PC.md",
    ".env.example",
    "INICIAR_APP.bat",
    "INICIAR_APP.ps1",
    "PARAR_APP.bat",
    "PARAR_APP.ps1",
    "BACKUP_BANCO.ps1",
    "BACKUP_DADOS_CRM.ps1",
    "ATUALIZAR_SEM_PERDER_DADOS.ps1",
    "INSTALAR_INICIAR_COM_WINDOWS.bat",
    "INSTALAR_INICIAR_COM_WINDOWS.ps1",
    "REMOVER_INICIAR_COM_WINDOWS.bat",
    "REMOVER_INICIAR_COM_WINDOWS.ps1",
    "LEIA_ANTES_DE_ABRIR.txt",
    "VERSAO_ATUALIZADA.txt"
)

if (-not $SamePath) {
    foreach ($file in $files) {
        $from = Join-Path $SourceAppPath $file
        if (Test-Path -LiteralPath $from) {
            Copy-Item -LiteralPath $from -Destination (Join-Path $TargetAppPath $file) -Force
        }
    }

    foreach ($folder in @("static", "templates")) {
        $from = Join-Path $SourceAppPath $folder
        if (Test-Path -LiteralPath $from) {
            Copy-Item -LiteralPath $from -Destination $TargetAppPath -Recurse -Force
        }
    }
} else {
    Write-Host "Fonte e destino sao a mesma pasta; apenas o backup preventivo foi criado." -ForegroundColor Yellow
}

Write-Host "Atualizacao concluida sem sobrescrever dados." -ForegroundColor Green
Write-Host "Dados preservados em: $DataDir"
Write-Host "Backup previo salvo em: $backupDir"
Write-Host ""
Write-Host "Agora rode INICIAR_APP.bat no destino."
