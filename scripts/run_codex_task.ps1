param(
    [Parameter(Mandatory = $true)]
    [string]$TaskName
)

$ErrorActionPreference = "Stop"

$taskFile = Join-Path (Join-Path $PSScriptRoot "..\codex_tasks") "$TaskName.md"

if (-not (Test-Path -LiteralPath $taskFile)) {
    throw "Task file not found: $taskFile"
}

$prompt = Get-Content -LiteralPath $taskFile -Raw -Encoding UTF8
codex exec $prompt
