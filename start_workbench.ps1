param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
$Workbench = Join-Path $ProjectRoot "workbench"
$ReactScripts = Join-Path $Workbench "node_modules\.bin\react-scripts.cmd"
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$ApiArgs = @("-m", "uvicorn", "research_agent.app:app", "--host", "127.0.0.1", "--port", "8877")

Write-Output "[api] $Python $($ApiArgs -join ' ')"
Write-Output "[workbench] npm --prefix $Workbench start"
if ($DryRun) { return }
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing Python runtime: $Python. FastAPI/Uvicorn must be installed there." }
if (-not $Npm) { throw "Missing npm command. Install Node.js before starting the React workbench." }
if (-not (Test-Path -LiteralPath $ReactScripts)) { throw "Missing local React artifact: $ReactScripts. This no-install bootstrap will not download it; provide the workbench node_modules dependencies offline first." }

$ApiProcess = $null
$WorkbenchProcess = $null
try {
    $ApiProcess = Start-Process -FilePath $Python -ArgumentList $ApiArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $WorkbenchProcess = Start-Process -FilePath $Npm.Source -ArgumentList @("--prefix", $Workbench, "start") -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
} catch {
    if ($ApiProcess) { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($WorkbenchProcess) { Stop-Process -Id $WorkbenchProcess.Id -Force -ErrorAction SilentlyContinue }
    throw
}
Write-Output "[api pid] $($ApiProcess.Id)"
Write-Output "[workbench pid] $($WorkbenchProcess.Id)"
