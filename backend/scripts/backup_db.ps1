<#
Full backup of the production database into one file (pg_dump custom format).

  powershell -ExecutionPolicy Bypass -File backend\scripts\backup_db.ps1

Needs:
  - $env:RUNWIN_DB_URL = the "External Database URL" from Render (dashboard > database > Connect).
    Keep it in a user environment variable, never in a file or in git.
  - PostgreSQL client tools (pg_dump 16 or newer), by default in D:\Gaming-platform-backups\tools\pgsql\bin.

Writes D:\Gaming-platform-backups\runwin-db-<date>_<time>.dump and keeps the newest $Keep files.
Restore into an empty database:
  pg_restore --no-owner --no-privileges --dbname "<new database URL>" runwin-db-....dump
#>
param(
    [string]$OutDir = "D:\Gaming-platform-backups",
    [string]$PgBin = "D:\Gaming-platform-backups\tools\pgsql\bin",
    [int]$Keep = 14
)
$ErrorActionPreference = "Stop"

$url = $env:RUNWIN_DB_URL
if (-not $url) { throw "Set RUNWIN_DB_URL to the External Database URL from Render first." }
$uri = [Uri]$url
$user, $password = $uri.UserInfo.Split(":", 2)
$database = $uri.AbsolutePath.TrimStart("/")
$port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }

# Connect over IPv4: on this network IPv6 leaves from an address that is not on Render's allow list
$ipv4 = [System.Net.Dns]::GetHostAddresses($uri.Host) | Where-Object { $_.AddressFamily -eq "InterNetwork" } | Select-Object -First 1

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$file = Join-Path $OutDir ("runwin-db-{0}.dump" -f (Get-Date -Format "yyyy-MM-dd_HHmm"))

$env:PGPASSWORD = [Uri]::UnescapeDataString($password)
$env:PGSSLMODE = "require"
$env:PGCONNECT_TIMEOUT = "30"
if ($ipv4) { $env:PGHOSTADDR = $ipv4.IPAddressToString }
try {
    & (Join-Path $PgBin "pg_dump.exe") --host $uri.Host --port $port --username ([Uri]::UnescapeDataString($user)) `
        --dbname $database --format=custom --compress=9 --no-owner --no-privileges --file $file
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
} finally {
    Remove-Item Env:PGPASSWORD, Env:PGHOSTADDR -ErrorAction SilentlyContinue
}

$sizeMb = [math]::Round((Get-Item $file).Length / 1MB, 2)
Write-Host "Backup saved: $file ($sizeMb MB)"

# Keep only the newest $Keep backups
Get-ChildItem $OutDir -Filter "runwin-db-*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | Remove-Item
