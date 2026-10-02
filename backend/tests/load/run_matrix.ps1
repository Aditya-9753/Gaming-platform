param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Duration = "2m"
)

$ErrorActionPreference = "Stop"
foreach ($users in @(100, 250, 500, 750, 1000)) {
    Write-Host "Running k6 REST + WebSocket load test for $users users"
    k6 run `
        -e "BASE_URL=$BaseUrl" `
        -e "DURATION=$Duration" `
        -e "USERS=$users" `
        (Join-Path $PSScriptRoot "k6_games.js")
    if ($LASTEXITCODE -ne 0) {
        throw "Load-test thresholds failed for $users users"
    }
}
