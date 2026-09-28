#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [switch]$Serve,
    [switch]$Watch,
    [switch]$Test,
    [switch]$Coverage,
    [ValidateRange(1, 65535)] [int]$Port = 4200,
    [string]$ProxyConfig = 'proxy.conf.json'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $root 'frontend'
$metadata = Join-Path $frontend 'public/build-metadata.json'
$brandSource = Join-Path $root 'brand'
$brandPublic = Join-Path $frontend 'public/brand'
$brandStyles = Join-Path $frontend 'src/brand'
$created = [System.Collections.Generic.List[string]]::new()
$rootHash = [System.Convert]::ToHexString(
    [System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($root))
).ToLowerInvariant()
$lockPath = Join-Path ([System.IO.Path]::GetTempPath()) "lzug-frontend-build-$rootHash.lock"
$lock = $null

while ($null -eq $lock) {
    try {
        $lock = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch [System.IO.IOException] {
        Start-Sleep -Milliseconds 100
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

try {
    if (-not (Test-Path -LiteralPath $metadata -PathType Leaf)) {
        $revision = (& git -C $root rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Unable to determine the Git revision.' }
        Invoke-Native 'uv' @('run', '--locked', '--extra', 'dev', 'python', '-m', 'backend.version', '--revision', $revision, '--output', $metadata)
        $created.Add($metadata)
    }

    if (-not (Test-Path -LiteralPath $brandPublic -PathType Container)) {
        New-Item -ItemType Directory -Path $brandPublic | Out-Null
        $created.Add($brandPublic)
    }
    if (-not (Test-Path -LiteralPath $brandStyles -PathType Container)) {
        New-Item -ItemType Directory -Path $brandStyles | Out-Null
        $created.Add($brandStyles)
    }
    $tokens = Join-Path $brandStyles 'tokens.css'
    if (-not (Test-Path -LiteralPath $tokens -PathType Leaf)) {
        Copy-Item (Join-Path $brandSource 'tokens.css') $tokens
        $created.Add($tokens)
    }
    foreach ($asset in @('favicon.svg', 'logo-mark-dark.svg')) {
        $destination = Join-Path $brandPublic $asset
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            Copy-Item (Join-Path $root "brand/derived/$asset") $destination
            $created.Add($destination)
        }
    }
    $favicon = Join-Path $frontend 'public/favicon.ico'
    if (-not (Test-Path -LiteralPath $favicon -PathType Leaf)) {
        Copy-Item (Join-Path $root 'brand/derived/favicon.ico') $favicon
        $created.Add($favicon)
    }

    $configuration = if ($env:LZUG_FRONTEND_CONFIGURATION) { $env:LZUG_FRONTEND_CONFIGURATION } else { 'production' }
    if ($configuration -notin @('production', 'demo')) {
        throw "Unsupported frontend configuration: $configuration"
    }
    Push-Location $root
    try {
        Invoke-Native 'task' @('frontend:transport:generate')
    } finally {
        Pop-Location
    }
    Push-Location $frontend
    try {
        if ($Serve) {
            Invoke-Native 'node' @('node_modules/@angular/cli/bin/ng.js', 'serve', '--proxy-config', $ProxyConfig, '--poll', '1000', '--host', '127.0.0.1', '--port', "$Port")
        } elseif ($Watch) {
            Invoke-Native 'node' @('node_modules/@angular/cli/bin/ng.js', 'build', '--watch', '--configuration', 'development')
        } elseif ($Test) {
            $testArguments = @('node_modules/@angular/cli/bin/ng.js', 'test', '--watch=false')
            if ($Coverage) { $testArguments += '--coverage' }
            Invoke-Native 'node' $testArguments
        } else {
            Invoke-Native 'node' @('node_modules/@angular/cli/bin/ng.js', 'build', '--configuration', $configuration)
        }
    } finally {
        Pop-Location
    }
} finally {
    foreach ($path in $created | Sort-Object Length -Descending) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force }
        elseif (Test-Path -LiteralPath $path -PathType Container) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }
    }
    $lock.Dispose()
}
