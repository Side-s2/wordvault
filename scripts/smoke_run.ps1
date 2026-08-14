# GUI 冒烟测试：以临时数据目录启动应用，自动切页后关闭。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "C:\Users\Side_\AppData\Local\Programs\Python\Python313\python.exe"
$dataDir = Join-Path $root "data_smoke"
$out = Join-Path $root "smoke_out.txt"
$err = Join-Path $root "smoke_err.txt"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
Remove-Item $out, $err -ErrorAction SilentlyContinue
$env:WORDVAULT_DATA_DIR = $dataDir

$proc = Start-Process -FilePath $py `
    -ArgumentList "main.py", "--smoke-test" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -WindowStyle Hidden `
    -PassThru

$deadline = (Get-Date).AddSeconds(45)
$done = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    if ($proc.HasExited) { break }
    if (Test-Path $out) {
        $text = Get-Content $out -Raw -ErrorAction SilentlyContinue
        if ($text -match "SMOKE_OK" -or $text -match "SMOKE_STATS_DONE" -or $text -match "SMOKE_FAIL") {
            $done = $true
            Start-Sleep -Seconds 1
            break
        }
    }
}

if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

Write-Output "=== stdout ==="
Get-Content $out -ErrorAction SilentlyContinue
Write-Output "=== stderr (tail) ==="
Get-Content $err -ErrorAction SilentlyContinue | Select-Object -Last 25

$text = Get-Content $out -Raw -ErrorAction SilentlyContinue
if ($text -match "SMOKE_OK" -or $text -match "SMOKE_STATS_DONE") {
    Write-Output "SMOKE_RESULT=PASS"
} else {
    Write-Output "SMOKE_RESULT=FAIL"
    exit 1
}
