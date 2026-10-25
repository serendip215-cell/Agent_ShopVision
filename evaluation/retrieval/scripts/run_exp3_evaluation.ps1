param(
    [string]$Python = "python",
    [string]$Config = "evaluation/retrieval/configs/exp3_acceleration.json",
    [string]$RunId = "",
    [switch]$Overwrite,
    [switch]$SkipPlots
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Push-Location $repoRoot
try {
    $arguments = @("evaluation/retrieval/code/evaluate_acceleration.py", "--config", $Config)
    if ($RunId) { $arguments += @("--run-id", $RunId) }
    if ($Overwrite) { $arguments += "--overwrite" }
    if ($SkipPlots) { $arguments += "--skip-plots" }
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "实验三评测未正常完成（退出码 $LASTEXITCODE），请查看上方错误或验收表。"
    }
}
finally {
    Pop-Location
}
