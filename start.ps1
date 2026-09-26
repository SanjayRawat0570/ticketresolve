<#
    Start Ticket Resolver.

        .\start.ps1

    Starts TrueForge if it isn't already up, provisions the agent, and runs
    the health check. Safe to re-run - nothing here is destructive.
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$BaseUrl = "http://localhost:8790"

function Test-TrueForge {
    try {
        Invoke-RestMethod "$BaseUrl/api/v1/capabilities" -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

# 1. Node version -----------------------------------------------------------
$nodeVersion = (node -v) -replace '^v', ''
$major = [int]($nodeVersion -split '\.')[0]
$minor = [int]($nodeVersion -split '\.')[1]
if ($major -lt 22 -or ($major -eq 22 -and $minor -lt 14)) {
    Write-Host "Node $nodeVersion is too old - TrueForge needs >= 22.14" -ForegroundColor Red
    exit 1
}
Write-Host "node v$nodeVersion" -ForegroundColor DarkGray

# 2. TrueForge --------------------------------------------------------------
if (Test-TrueForge) {
    Write-Host "TrueForge already running at $BaseUrl" -ForegroundColor DarkGray
} else {
    Write-Host "starting TrueForge..." -ForegroundColor DarkGray
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command", "npx -y @truefoundry/trueforge"
    ) -WindowStyle Minimized

    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if (Test-TrueForge) { break }
        Start-Sleep -Seconds 2
    }
    if (-not (Test-TrueForge)) {
        Write-Host "TrueForge did not come up within 120s." -ForegroundColor Red
        Write-Host "Run 'npx @truefoundry/trueforge' manually to see the error."
        exit 1
    }
    Write-Host "TrueForge up at $BaseUrl" -ForegroundColor DarkGray
}

# 3. Provision + verify -----------------------------------------------------
python setup.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nsetup.py failed - fix the error above, then re-run." -ForegroundColor Red
    exit 1
}

python verify.py
$verifyOk = ($LASTEXITCODE -eq 0)

Write-Host ""
if ($verifyOk) {
    Write-Host "Ready. Open $BaseUrl and start a session with 'ticket-resolver'." -ForegroundColor Green
    Write-Host "Or from the terminal:"
    Write-Host "    python run_ticket.py SAN-5     reproduce -> patch -> approval"
    Write-Host "    python run_ticket.py SAN-6     honest 'could not reproduce'"
} else {
    Write-Host "Some checks failed - see above." -ForegroundColor Yellow
}
