param(
    [string]$Python = "python",
    [ValidateSet("auto", "cpu", "cuda")]
    [string]$Device = "cuda",
    [int]$PerCategory = 5,
    [string]$RunId = "",
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot
if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = "gpt_pilot_$(Get-Date -Format 'yyyyMMdd_HHmmssfff')"
}

$arguments = @(
    "evaluation\retrieval\code\run_gpt61sol_pilot.py",
    "--per-category", $PerCategory,
    "--device", $Device,
    "--run-id", $RunId
)
if ($Resume) {
    $arguments += "--resume"
}

& $Python @arguments

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
