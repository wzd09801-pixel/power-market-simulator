$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$projectSuffix = "{0}-{1}" -f $PID, (Get-Date -Format "yyyyMMddHHmmss")
$projectName = "eee-no-data-$projectSuffix".ToLowerInvariant()
$ready = $false
$script:allocatedPorts = @()

function New-TrialTcpPort {
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
    throw "Unable to allocate an available no-data trial TCP port."
}

function Invoke-TrialJson {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$Method = "GET"
    )
    if ($Method -eq "POST") {
        return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json"
    }
    return Invoke-RestMethod -Method Get -Uri $Uri
}

function Assert-TrialCondition {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

$postgresPort = New-TrialTcpPort
$apiPort = New-TrialTcpPort
$cockpitPort = New-TrialTcpPort
$minioPort = New-TrialTcpPort
$minioConsolePort = New-TrialTcpPort
$environmentOverrides = @{
    "POSTGRES_PORT" = $postgresPort
    "API_PORT" = $apiPort
    "COCKPIT_PORT" = $cockpitPort
    "MINIO_PORT" = $minioPort
    "MINIO_CONSOLE_PORT" = $minioConsolePort
}
$previousEnvironment = @{}

foreach ($name in $environmentOverrides.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name, $environmentOverrides[$name])
}

$apiBaseUrl = "http://127.0.0.1:$apiPort"
$apiHealthUrl = "$apiBaseUrl/healthz"
$readinessUrl = "$apiBaseUrl/v1/system/readiness"
$operationsReviewPackageUrl = "$apiBaseUrl/v1/operations/review-package"
$seedJobUrl = "$apiBaseUrl/v1/operations/jobs/demo_research_workspace_seed/run"

Push-Location $workspace
try {
    Write-Host "Starting isolated no-data validation stack: $projectName"
    Write-Host "API: $apiBaseUrl"
    docker compose -p $projectName up --build -d db minio api operation-worker cockpit
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE."
    }

    for ($attempt = 0; $attempt -lt 90; $attempt += 1) {
        try {
            Invoke-WebRequest -UseBasicParsing $apiHealthUrl | Out-Null
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $ready) {
        docker compose -p $projectName ps
        docker compose -p $projectName logs --tail 160 api operation-worker
        throw "No-data validation API did not become healthy."
    }

    $emptyReadiness = Invoke-TrialJson -Uri $readinessUrl
    Assert-TrialCondition ($emptyReadiness.status -eq "warning") "Expected empty readiness status warning."
    Assert-TrialCondition ($emptyReadiness.no_auto_trading -eq $true) "Expected no_auto_trading=true on empty readiness."
    Assert-TrialCondition ($emptyReadiness.missing_demo_items.Count -gt 0) "Expected empty database to list missing demo items."
    $isolation = $emptyReadiness.checks | Where-Object { $_.key -eq "recommendation_isolation" } | Select-Object -First 1
    Assert-TrialCondition ($null -ne $isolation) "Expected recommendation_isolation readiness check."
    Assert-TrialCondition ($isolation.status -eq "healthy") "Expected recommendation isolation to stay healthy on empty database."

    $seedRun = Invoke-TrialJson -Method "POST" -Uri $seedJobUrl
    Assert-TrialCondition ($seedRun.workflow_key -eq "demo_research_workspace_seed") "Expected demo seed workflow key."
    Assert-TrialCondition ($seedRun.status -in @("queued", "running", "succeeded", "skipped")) "Unexpected demo seed initial status: $($seedRun.status)."

    $runUrl = "$apiBaseUrl/v1/operations/runs/$($seedRun.workflow_run_id)"
    $finalRun = $null
    for ($attempt = 0; $attempt -lt 90; $attempt += 1) {
        $candidate = Invoke-TrialJson -Uri $runUrl
        if ($candidate.status -in @("succeeded", "skipped", "failed")) {
            $finalRun = $candidate
            break
        }
        Start-Sleep -Seconds 2
    }
    Assert-TrialCondition ($null -ne $finalRun) "Timed out waiting for demo seed workflow completion."
    Assert-TrialCondition ($finalRun.status -eq "succeeded") "Expected demo seed to succeed, got $($finalRun.status): $($finalRun.error_code) $($finalRun.error_message)"
    Assert-TrialCondition ($finalRun.summary.no_auto_trading -eq $true) "Expected demo seed summary no_auto_trading=true."

    $seededReadiness = Invoke-TrialJson -Uri $readinessUrl
    Assert-TrialCondition ($seededReadiness.no_auto_trading -eq $true) "Expected no_auto_trading=true after seed."
    Assert-TrialCondition ($seededReadiness.missing_demo_items.Count -eq 0) "Expected no missing demo items after seed."
    $demoSeedCheck = $seededReadiness.checks | Where-Object { $_.key -eq "demo_seed" } | Select-Object -First 1
    Assert-TrialCondition ($null -ne $demoSeedCheck) "Expected demo_seed readiness check."
    Assert-TrialCondition ($demoSeedCheck.status -eq "healthy") "Expected demo_seed readiness check to be healthy."
    $seededIsolation = $seededReadiness.checks | Where-Object { $_.key -eq "recommendation_isolation" } | Select-Object -First 1
    Assert-TrialCondition ($seededIsolation.status -eq "healthy") "Expected recommendation isolation to stay healthy after seed."

    $operationsPackage = Invoke-TrialJson -Uri $operationsReviewPackageUrl
    Assert-TrialCondition ($operationsPackage.no_auto_trading -eq $true) "Expected operations package no_auto_trading=true."
    Assert-TrialCondition ($operationsPackage.manual_job_keys_only -eq $true) "Expected manual_job_keys_only=true."
    Assert-TrialCondition ($operationsPackage.fetch_performed -eq $false) "Expected operations package fetch_performed=false."
    Assert-TrialCondition ($operationsPackage.network_probe_performed -eq $false) "Expected operations package network_probe_performed=false."

    Write-Host "No-data validation succeeded."
    Write-Host "Project $projectName was stopped; volumes are retained for inspection."
}
catch {
    Write-Warning "No-data validation failed. If Docker image pulls failed, treat that as an external network blocker. $($_.Exception.Message)"
    throw
}
finally {
    docker compose -p $projectName stop cockpit operation-worker api minio db
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name])
    }
    Pop-Location
}
