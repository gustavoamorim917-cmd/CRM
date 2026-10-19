param(
    [switch]$NoBrowser,
    [switch]$FixedPort,
    [int]$PreferredPort = 5003
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$ExpectedBuild = "20260505-dados-persistentes-v1"
$CoreDependencyProbe = @"
import flask, pandas, openpyxl
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
"@

function Backup-CrmDatabase {
    $dbPath = Join-Path $PSScriptRoot "data\crm.sqlite3"
    if (-not (Test-Path -LiteralPath $dbPath)) {
        return
    }

    $backupDir = Join-Path $PSScriptRoot "data\backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = Join-Path $backupDir "crm_backup_$stamp.sqlite3"
    Copy-Item -LiteralPath $dbPath -Destination $backupPath -Force
    Write-Host "Backup do banco salvo em: $backupPath" -ForegroundColor Green
}

function Find-Python {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates = @(
        @{ File = $bundledPython; Args = @() },
        @{ File = "py"; Args = @("-3") },
        @{ File = "python"; Args = @() }
    )

    $firstValid = $null
    foreach ($candidate in $candidates) {
        try {
            if ($candidate.File -match "\\|/" -and -not (Test-Path -LiteralPath $candidate.File)) {
                continue
            }
            & $candidate.File @($candidate.Args) --version *> $null
            if ($LASTEXITCODE -eq 0) {
                if (-not $firstValid) {
                    $firstValid = $candidate
                }
                if (Test-PythonCoreDependencies $candidate) {
                    return $candidate
                }
            }
        } catch {
            continue
        }
    }

    if ($firstValid) {
        return $firstValid
    }

    throw "Python 3 nao encontrado. Instale o Python 3 e marque a opcao 'Add python.exe to PATH'."
}

function Test-PythonCode($Python, [string]$Code) {
    try {
        & $Python.File @($Python.Args) -c $Code *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-PythonCoreDependencies($Python) {
    return Test-PythonCode $Python $CoreDependencyProbe
}

function Test-FreePort([int]$Port) {
    $listener = $null
    try {
        $address = [System.Net.IPAddress]::Parse("127.0.0.1")
        $listener = [System.Net.Sockets.TcpListener]::new($address, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Find-FreePort {
    if ($env:PORT) {
        $requested = [int]$env:PORT
        if (Test-FreePort $requested) {
            return $requested
        }
        if (Test-AppHealth $requested) {
            return $requested
        }
        if ($FixedPort) {
            throw "A porta $requested esta ocupada por outro processo."
        }
        Write-Host "Porta $requested ocupada. Procurando outra porta livre..." -ForegroundColor Yellow
    }

    if (Test-FreePort $PreferredPort) {
        return $PreferredPort
    }
    if (Test-AppHealth $PreferredPort) {
        return $PreferredPort
    }
    if ($FixedPort) {
        throw "A porta $PreferredPort esta ocupada por outro processo."
    }

    foreach ($port in 5000..5020) {
        if (Test-FreePort $port) {
            return $port
        }
        if (Test-AppHealth $port) {
            return $port
        }
    }

    throw "Nenhuma porta livre encontrada entre 5000 e 5020."
}

function Test-AppHealth([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1 -UseBasicParsing
        $data = $response.Content | ConvertFrom-Json
        return $data.ok -and $data.build -eq $ExpectedBuild
    } catch {
        return $false
    }
}

function Invoke-Python($Python, [string[]]$Arguments) {
    & $Python.File @($Python.Args) @Arguments
    return $LASTEXITCODE
}

$python = Find-Python
$port = Find-FreePort
$env:PORT = "$port"
$url = "http://127.0.0.1:$port"

if (Test-AppHealth $port) {
    if (-not $NoBrowser) {
        Start-Process $url
    }
    Write-Host "O app ja esta rodando em $url" -ForegroundColor Green
    if (-not $NoBrowser) {
        Read-Host "Pressione Enter para fechar esta janela"
    }
    exit 0
}

Backup-CrmDatabase

Write-Host ""
Write-Host "SP Imoveis CRM / WhatsApp" -ForegroundColor Cyan
Write-Host "Endereco: $url" -ForegroundColor Green
Write-Host "Nao feche esta janela enquanto estiver usando o app." -ForegroundColor Yellow
Write-Host ""

Write-Host "Verificando dependencias..." -ForegroundColor Cyan
if (-not (Test-PythonCoreDependencies $python)) {
    Write-Host "Instalando dependencias..." -ForegroundColor Cyan
    Invoke-Python $python @("-m", "pip", "install", "--upgrade", "-r", "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Nao foi possivel instalar todas as dependencias automaticamente." -ForegroundColor Yellow
    }
}
if (-not (Test-PythonCoreDependencies $python)) {
    Write-Host "Reinstalando Selenium..." -ForegroundColor Cyan
    Invoke-Python $python @("-m", "pip", "install", "--upgrade", "--force-reinstall", "selenium>=4.18.0")
    if ($LASTEXITCODE -ne 0 -or -not (Test-PythonCoreDependencies $python)) {
        throw "Falha ao preparar Selenium. Execute: python -m pip install --upgrade --force-reinstall selenium"
    }
}

$waiter = Start-Job -ScriptBlock {
    param($Url, $OpenBrowser, $ExpectedBuild)
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "$Url/api/health" -TimeoutSec 1 -UseBasicParsing
            $data = $response.Content | ConvertFrom-Json
            if ($data.ok -and $data.build -eq $ExpectedBuild) {
                if ($OpenBrowser) {
                    Start-Process $Url
                }
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
} -ArgumentList $url, (-not $NoBrowser), $ExpectedBuild

try {
    Invoke-Python $python @("app.py")
} finally {
    Receive-Job $waiter -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $waiter -Force -ErrorAction SilentlyContinue
    if (-not $NoBrowser) {
        Write-Host ""
        Write-Host "Servidor parado. Para usar novamente, execute INICIAR_APP.bat." -ForegroundColor Yellow
        Read-Host "Pressione Enter para fechar"
    }
}
