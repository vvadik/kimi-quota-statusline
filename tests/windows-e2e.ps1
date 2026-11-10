#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$workDir = Join-Path $env:TEMP 'kqs-windows-e2e'
if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

$savedUserProfile = $env:USERPROFILE
$savedHome = $env:HOME
$savedKimiHome = $env:KIMI_CODE_HOME
$env:USERPROFILE = Join-Path $workDir 'fake-home'
$env:HOME = $env:USERPROFILE
$env:KIMI_CODE_HOME = Join-Path $env:USERPROFILE '.kimi-code'
$env:KIMI_SL_NOCOLOR = '1'
New-Item -ItemType Directory -Force -Path $env:KIMI_CODE_HOME | Out-Null

try {
    $py = (Get-Command python -ErrorAction Stop).Source
    $statusline = Join-Path (Split-Path -Parent $PSScriptRoot) 'statusline.py'
    $payload = '{"model":"K3.1 Pro","cwd":"C:/пользователь/мой проект","gitBranch":"hidden","permissionMode":"auto","sessionId":"","version":"e2e"}'
    $out = $payload | & $py $statusline
    if ($LASTEXITCODE -ne 0 -or $out -notlike '*K3.1 Pro*' -or $out -notlike '*5h*' -or
        $out -notlike '*7d*' -or $out -like '*hidden*') {
        throw "Unexpected status line: $out"
    }
    Write-Host "PASS native status and quota UTF-8 render: $out"

    $cache = Join-Path $env:KIMI_CODE_HOME 'statusline-quota.json'
    $lock = Join-Path $env:KIMI_CODE_HOME 'statusline-quota-refresh.lock'
    $ready = $false
    for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
        Start-Sleep -Milliseconds 250
        $ready = (Test-Path $cache) -and -not (Test-Path $lock)
    }
    if (-not $ready) { throw 'Detached refresh did not write cache and release its lock' }
    $data = Get-Content $cache -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $data.attempt_at -or $null -eq $data.fetched_at) {
        throw 'Refresh cache is missing attempt/fetch timestamps'
    }
    Write-Host 'PASS short-lived refresh wrote cache and exited'

    & $py (Join-Path (Split-Path -Parent $PSScriptRoot) 'install.py')
    if ($LASTEXITCODE -ne 0) { throw 'Install failed' }
    & $py (Join-Path (Split-Path -Parent $PSScriptRoot) 'uninstall.py')
    if ($LASTEXITCODE -ne 0) { throw 'Uninstall failed' }
    if (Test-Path $cache) { throw 'Uninstall left quota cache behind' }
    Write-Host 'PASS install/uninstall roundtrip'
}
finally {
    $env:USERPROFILE = $savedUserProfile
    $env:HOME = $savedHome
    $env:KIMI_CODE_HOME = $savedKimiHome
    Remove-Item -Recurse -Force $workDir -ErrorAction SilentlyContinue
}
