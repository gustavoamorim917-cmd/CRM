$ports = 5000..5020
$stopped = @()

foreach ($port in $ports) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($connection in $connections) {
            $pidValue = $connection.OwningProcess
            if ($pidValue -and ($stopped -notcontains $pidValue)) {
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                $stopped += $pidValue
                Write-Host "Servidor na porta $port encerrado. PID: $pidValue"
            }
        }
    } catch {
        Write-Host "Nao foi possivel verificar a porta $port."
    }
}

if (-not $stopped.Count) {
    Write-Host "Nenhum servidor local do app encontrado nas portas 5000 a 5020."
}
