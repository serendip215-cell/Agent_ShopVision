param(
    [string]$Python = "python",
    [ValidateSet("auto", "cpu", "cuda")]
    [string]$Device = "auto"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot

& $Python evaluation\retrieval\code\evaluate_retrieval.py `
    --queries evaluation/retrieval/test_data/queries_smoke.csv `
    --qrels evaluation/retrieval/test_data/qrels_smoke.csv `
    --top-k 10 `
    --candidate-k 50 `
    --device $Device

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
