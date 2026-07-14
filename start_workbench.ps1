param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
$Workbench = Join-Path $ProjectRoot "workbench"
$ReactScripts = Join-Path $Workbench "node_modules\.bin\react-scripts.cmd"
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$ApiArgs = @("-m", "uvicorn", "research_agent.app:app", "--host", "127.0.0.1", "--port", "8877")
$ApiBase = "http://127.0.0.1:8877"

Write-Output "[api] $Python $($ApiArgs -join ' ')"
Write-Output "[workbench] npm --prefix $Workbench start"
if ($DryRun) { return }
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing Python runtime: $Python. FastAPI/Uvicorn must be installed there." }
if (-not $Npm) { throw "Missing npm command. Install Node.js before starting the React workbench." }
if (-not (Test-Path -LiteralPath $ReactScripts)) { throw "Missing local React artifact: $ReactScripts. This no-install bootstrap will not download it; provide the workbench node_modules dependencies offline first." }

$ApiProcess = $null
$WorkbenchProcess = $null
$ReuseApi = $false

$Listener = Get-NetTCPConnection -LocalPort 8877 -State Listen -ErrorAction SilentlyContinue
if ($Listener) {
    $Compatible = $false
    try {
        $Schema = Invoke-RestMethod -Uri "$ApiBase/openapi.json" -TimeoutSec 2
        $Paths = @($Schema.paths.PSObject.Properties.Name)
        $Compatible = $Paths -contains "/schedules" -and $Paths -contains "/runs/{run_id}/turns/stream"
    } catch {
        $Compatible = $false
    }
    if (-not $Compatible) {
        $OwnerIds = @($Listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "Port 8877 is occupied by an incompatible or stale backend (PID: $OwnerIds). Close it and run this script again."
    }
    $ReuseApi = $true
    Write-Output "[api] compatible backend already running; reusing port 8877"
}

try {
    if (-not $ReuseApi) {
        $ApiProcess = Start-Process -FilePath $Python -ArgumentList $ApiArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
        $Ready = $false
        foreach ($Attempt in 1..40) {
            try {
                $Health = Invoke-RestMethod -Uri "$ApiBase/health" -TimeoutSec 1
                if ($Health.status -eq "ok") { $Ready = $true; break }
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }
        if (-not $Ready) { throw "The backend did not become ready within 10 seconds." }
    }
    $WorkbenchProcess = Start-Process -FilePath $Npm.Source -ArgumentList @("--prefix", $Workbench, "start") -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
} catch {
    if ($ApiProcess) { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($WorkbenchProcess) { Stop-Process -Id $WorkbenchProcess.Id -Force -ErrorAction SilentlyContinue }
    throw
}
if ($ApiProcess) { Write-Output "[api pid] $($ApiProcess.Id)" }
Write-Output "[workbench pid] $($WorkbenchProcess.Id)"
