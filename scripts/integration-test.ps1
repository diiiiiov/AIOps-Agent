param(
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "..\docker-compose.integration.yml"
$python = Join-Path $PSScriptRoot "..\.runtime-venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .runtime-venv. Create it and install -e '.[dev]' first."
}

try {
    docker compose -f $composeFile up -d --wait

    $mcpProcesses = @()
    $env:MCP_HOST = "127.0.0.1"
    $env:MCP_PORT = "18003"
    $mcpProcesses += Start-Process -FilePath $python -ArgumentList "mcp_servers/cls_server.py" -PassThru -WindowStyle Hidden
    $env:MCP_PORT = "18004"
    $mcpProcesses += Start-Process -FilePath $python -ArgumentList "mcp_servers/monitor_server.py" -PassThru -WindowStyle Hidden

    foreach ($port in 18003, 18004) {
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try {
                $socket = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $port)
                $socket.Dispose()
                $ready = $true
                break
            }
            catch { Start-Sleep -Seconds 1 }
        }
        if (-not $ready) { throw "MCP server on port $port did not become ready" }
    }

    $env:RUN_INTEGRATION = "1"
    & $python -m pytest tests/test_integration_stack.py -v
    if ($LASTEXITCODE -ne 0) { throw "Integration tests failed with exit code $LASTEXITCODE" }
}
finally {
    if ($mcpProcesses) {
        $mcpProcesses | Where-Object { -not $_.HasExited } | Stop-Process
    }
    if (-not $KeepRunning) {
        docker compose -f $composeFile down --volumes --remove-orphans
    }
}
