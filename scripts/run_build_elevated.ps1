$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$log = Join-Path $root "build_log.txt"
$marker = Join-Path $root "build_exit_code.txt"
Remove-Item -LiteralPath $log, $marker -Force -ErrorAction SilentlyContinue

$env:JAVA_HOME = "C:\Users\Side_\java\17.0.13+11"
$env:ANDROID_HOME = "C:\Users\Side_\Android\sdk"
$env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
$env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:JAVA_TOOL_OPTIONS = "-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=7890 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=7890"
$product = "wordvault"
$fletExe = "C:\Users\Side_\AppData\Local\Programs\Python\Python313\Scripts\flet.exe"
$buildRoot = Join-Path $root "build\flutter\build"
$gradlew = Join-Path $root "build\flutter\android\gradlew.bat"

$exitCode = 1
$attempt = 0
while ($attempt -lt 3 -and $exitCode -ne 0) {
    $attempt++
    Add-Content -LiteralPath $log -Value "=== BUILD ATTEMPT $attempt ==="

    Get-ChildItem -LiteralPath $buildRoot -Recurse -Directory -Filter "compileReleaseKotlin" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName.StartsWith($buildRoot, [System.StringComparison]::OrdinalIgnoreCase) } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    & $fletExe build apk `
      --arch arm64-v8a `
      --android-legacy-packaging `
      --android-permissions INTERNET=true `
      --exclude data data_smoke ui_shots tools tests scripts .git __pycache__ `
      --project wordvault `
      --artifact wordvault `
      --product $product `
      --org com.vibecoding `
      --build-version 1.1.3 `
      --build-number 5 `
      --splash-color "#5B67F1" `
      --splash-dark-color "#1B1B2F" `
      --yes `
      --no-rich-output *>> $log

    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and $attempt -lt 3) {
        Add-Content -LiteralPath $log -Value "=== ATTEMPT $attempt FAILED (exit $exitCode), retrying ==="
        & $gradlew --stop *>> $log 2>&1
        Start-Sleep -Seconds 5
    }
}

Set-Content -LiteralPath $marker -Value "$exitCode"
