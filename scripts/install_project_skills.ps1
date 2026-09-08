param(
    [string]$Destination = "$env:USERPROFILE\.codex\skills",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$source = Join-Path (Join-Path $PSScriptRoot "..") ".codex\skills"

if (-not (Test-Path -LiteralPath $source)) {
    throw "Project skills directory not found: $source"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

Get-ChildItem -LiteralPath $source -Directory | ForEach-Object {
    $target = Join-Path $Destination $_.Name
    if (Test-Path -LiteralPath $target) {
        if (-not $Force) {
            throw "Skill already exists: $target. Re-run with -Force to overwrite."
        }
        $resolvedDestination = (Resolve-Path -LiteralPath $Destination).Path
        $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolvedTarget.StartsWith($resolvedDestination, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to overwrite path outside destination: $resolvedTarget"
        }
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
    Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse
}

Write-Host "Installed project skills to $Destination"
