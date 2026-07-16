param(
    [switch]$DryRun,
    [ValidateRange(1024, 65535)]
    [int]$ApiPort = 8878
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$FallbackPython = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
$Python = if (Test-Path -LiteralPath $ProjectPython) { $ProjectPython } else { $FallbackPython }
$Workbench = Join-Path $ProjectRoot "workbench"
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$ApiArgs = @("-m", "uvicorn", "research_agent.app:app", "--host", "127.0.0.1", "--port", "$ApiPort")
$ApiBase = "http://127.0.0.1:$ApiPort"

Write-Output "[api] $Python $($ApiArgs -join ' ')"
Write-Output "[workbench] npm start in '$Workbench'"
if ($DryRun) { return }
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing Python runtime: $Python. FastAPI/Uvicorn must be installed there." }
if (-not $Npm) { throw "Missing npm command. Install Node.js before starting the React workbench." }
$ExpectedVersion = (& $Python -c "from research_agent.version import RUNTIME_VERSION; print(RUNTIME_VERSION)").Trim()

$ApiProcess = $null
$WorkbenchProcess = $null
$ReuseApi = $false

$Listener = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue
if ($Listener) {
    $Compatible = $false
    try {
        $Health = Invoke-RestMethod -Uri "$ApiBase/health" -TimeoutSec 2
        $Schema = Invoke-RestMethod -Uri "$ApiBase/openapi.json" -TimeoutSec 2
        $Paths = @($Schema.paths.PSObject.Properties.Name)
        $Compatible = (
            $Health.version -eq $ExpectedVersion -and
            $Paths -contains "/schedules" -and
            $Paths -contains "/runs/{run_id}/turns/stream" -and
            $Paths -contains "/runs/{run_id}/intervene" -and
            $Paths -contains "/runs/{run_id}/artifacts/{artifact_name}"
        )
    } catch {
        $Compatible = $false
    }
    if (-not $Compatible) {
        $OwnerIds = @($Listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "Port $ApiPort is occupied by an incompatible or stale backend (PID: $OwnerIds). Close it or choose another -ApiPort."
    }
    $ReuseApi = $true
    Write-Output "[api] compatible backend already running; reusing port $ApiPort"
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
    $env:REACT_APP_API_BASE = $ApiBase
    $env:REACT_APP_API_PORT = "$ApiPort"
    $WorkbenchProcess = Start-Process -FilePath $Npm.Source -ArgumentList @("start") -WorkingDirectory $Workbench -WindowStyle Hidden -PassThru
} catch {
    if ($ApiProcess) { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($WorkbenchProcess) { Stop-Process -Id $WorkbenchProcess.Id -Force -ErrorAction SilentlyContinue }
    throw
}
if ($ApiProcess) { Write-Output "[api pid] $($ApiProcess.Id)" }
Write-Output "[workbench pid] $($WorkbenchProcess.Id)"
