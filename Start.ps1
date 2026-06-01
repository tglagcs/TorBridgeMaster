# Start.ps1
# Downloads the bridge list, runs the scanner, and opens the HTML report.

$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = 'https://raw.githubusercontent.com/Delta-Kronecker/Tor-Bridges-Collector/refs/heads/main/bridge/obfs4_tested.txt'
$br_file = Join-Path $workdir 'obfs4_tested.txt'

Write-Host "============================================================"
Write-Host "Tor Bridge Master"
Write-Host "============================================================"
Write-Host "Special thanks to:"
Write-Host "  https://github.com/Delta-Kronecker/Tor-Bridges-Collector"
Write-Host "  https://gist.github.com/Satyani/409d5f14a6cd2ab57024e5c7326ca78a"
Write-Host "============================================================"
Write-Host ""

# Download the bridge list
Write-Host "[*] Downloading bridges list..."
try {
    Invoke-WebRequest -Uri $url -OutFile $br_file -ErrorAction Stop
    Write-Host "[OK] Downloaded: $br_file" -ForegroundColor Green
} catch {
    Write-Host "[ERR] Failed to download: $_" -ForegroundColor Red
    pause
    exit 1
}

# Locate Python
$pythonCmd = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    try {
        $null = Get-Command $cmd -ErrorAction Stop
        $pythonCmd = $cmd
        break
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "[ERR] Python not found! Install Python 3 from python.org" -ForegroundColor Red
    Write-Host "      Make sure to check 'Add Python to PATH' during installation"
    pause
    exit 1
}

Write-Host "[*] Using Python: $pythonCmd`n"

# Run Main.py from the src folder
$scriptPath = Join-Path $workdir 'src\Main.py'
if (-not (Test-Path $scriptPath)) {
    Write-Host "[ERR] Main.py not found in $workdir\src" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[*] Starting bridge scanning (parallel)..."
& $pythonCmd $scriptPath --max-workers 10

# Open the HTML report
$htmlFile = Join-Path $workdir 'Best_Bridges.html'
if (Test-Path $htmlFile) {
    Write-Host "[*] Opening HTML report in browser..."
    Start-Process $htmlFile
} else {
    Write-Host "[!] HTML report not found." -ForegroundColor Yellow
}

Write-Host "`n[*] Done! Press any key to exit..."
pause
