param(
    [string]$Session = "",
    [string[]]$Message = @(),
    [switch]$New,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path -LiteralPath $BundledPython) { $BundledPython } else { "python" }
$ArgsList = @("-m", "research_agent.cli", "chat")

if (-not [string]::IsNullOrWhiteSpace($Session)) {
    $ArgsList += @("--session", $Session)
}
if ($New) {
    $ArgsList += "--new"
}
foreach ($Item in $Message) {
    $ArgsList += @("--message", $Item)
}

$env:PYTHONUTF8 = "1"
Push-Location $ProjectRoot
try {
    Write-Output "[agent] project: $ProjectRoot"
    Write-Output "[agent] mode: terminal chat"
    if ($DryRun) {
        Write-Output $Python
        Write-Output ($ArgsList -join " ")
        return
    }
    & $Python @ArgsList
} finally {
    Pop-Location
}
