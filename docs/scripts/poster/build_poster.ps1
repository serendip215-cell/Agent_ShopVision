# 一键渲染 ShopVision 期末宣传海报（2480x3508 px, ISO A 纸 300 DPI PNG）
param(
    [string]$OutPath = (Join-Path $PSScriptRoot "..\..\交付材料\期末_第23组\01_宣传海报\期末交付海报.png")
)

$ErrorActionPreference = "Stop"
$htmlFile = (Resolve-Path (Join-Path $PSScriptRoot "shopvision_poster.html")).Path
$htmlUri = "file:///" + ($htmlFile -replace "\\", "/")
$outFull = [System.IO.Path]::GetFullPath($OutPath)
New-Item -ItemType Directory -Force -Path (Split-Path $outFull) | Out-Null

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$browser = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    throw "未找到 Chrome 或 Edge，无法执行无头高分辨率渲染。"
}

$tmpProfile = Join-Path ([System.IO.Path]::GetTempPath()) ("shopvision_poster_prof_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmpProfile | Out-Null

try {
    $argsList = @(
        "--headless=new",
        "--user-data-dir=$tmpProfile",
        "--disable-gpu",
        "--no-sandbox",
        "--allow-file-access-from-files",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        "--window-size=1240,1754",
        "--virtual-time-budget=3000",
        "--screenshot=$outFull",
        $htmlUri
    )
    $proc = Start-Process -FilePath $browser -ArgumentList $argsList -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0 -or -not (Test-Path $outFull)) {
        throw "渲染失败，ExitCode=$($proc.ExitCode)"
    }
    Add-Type -AssemblyName System.Drawing
    $img = [System.Drawing.Image]::FromFile($outFull)
    $mb = [math]::Round((Get-Item $outFull).Length / 1MB, 2)
    Write-Output "海报渲染成功: $outFull ($($img.Width) x $($img.Height), $mb MB)"
    $img.Dispose()
} finally {
    Remove-Item -Recurse -Force $tmpProfile -ErrorAction SilentlyContinue
}
