$ErrorActionPreference = "Stop"

$projectName = "eee-smoke"
$workspace = Split-Path -Parent $PSScriptRoot
$webapp = Join-Path $workspace "webapp"
$ready = $false
$script:allocatedPorts = @()

function New-SmokeTcpPort {
    for ($attempt = 0; $attempt -lt 50; $attempt += 1) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, 0)
        try {
            $listener.Start()
            $port = $listener.LocalEndpoint.Port
            if ($script:allocatedPorts -notcontains $port) {
                $script:allocatedPorts += $port
                return [string]$port
            }
        }
        finally {
            $listener.Stop()
        }
    }
    throw "Unable to allocate an available smoke-test TCP port."
}

$postgresPort = New-SmokeTcpPort
$apiPort = New-SmokeTcpPort
$cockpitPort = New-SmokeTcpPort
$minioPort = New-SmokeTcpPort
$minioConsolePort = New-SmokeTcpPort
$environmentOverrides = @{
    "POSTGRES_PORT" = $postgresPort
    "API_PORT" = $apiPort
    "COCKPIT_PORT" = $cockpitPort
    "MINIO_PORT" = $minioPort
    "MINIO_CONSOLE_PORT" = $minioConsolePort
    "PLAYWRIGHT_BASE_URL" = "http://127.0.0.1:$cockpitPort"
}
$previousEnvironment = @{}

foreach ($name in $environmentOverrides.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name, $environmentOverrides[$name])
}
$cockpitHealthUrl = "$($environmentOverrides["PLAYWRIGHT_BASE_URL"])/healthz"

Push-Location $workspace
try {
    Write-Host "Starting isolated Compose smoke stack: $projectName"
    docker compose -p $projectName up --build -d db minio api operation-worker cockpit
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE."
    }

    for ($attempt = 0; $attempt -lt 90; $attempt += 1) {
        try {
            Invoke-WebRequest -UseBasicParsing $cockpitHealthUrl | Out-Null
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $ready) {
        docker compose -p $projectName ps
        docker compose -p $projectName logs --tail 120 api operation-worker cockpit
        throw "Compose smoke stack did not become healthy."
    }

    Push-Location $webapp
    try {
        npm run test:e2e
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright smoke tests failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Warning "Compose smoke failed. If Docker image pulls failed, treat that as an external network blocker. $($_.Exception.Message)"
    throw
}
finally {
    docker compose -p $projectName stop cockpit operation-worker api minio db
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name])
    }
    Pop-Location
}
