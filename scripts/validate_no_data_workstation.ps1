$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$trialSuite = Join-Path $PSScriptRoot "validate_no_data_trial_suite.ps1"
$webappDir = Join-Path $repoRoot "webapp"

Write-Host "Running no-data host-only trial suite..."
& $trialSuite

Write-Host "Running no-data cockpit workspace smoke..."
Push-Location $webappDir
try {
    npm run test:e2e:no-data-workspaces
}
finally {
    Pop-Location
}

Write-Host "No-data workstation validation succeeded."
