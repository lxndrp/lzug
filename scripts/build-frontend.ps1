#!/usr/bin/env pwsh

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $root 'frontend'
$metadata = Join-Path $frontend 'public/build-metadata.json'
$brandPublic = Join-Path $frontend 'public/brand'
$created = [System.Collections.Generic.List[string]]::new()

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
        $python = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'python3' }
        Invoke-Native $python @(
            (Join-Path $root 'scripts/build_metadata.py'),
            '--revision', $revision,
            '--output', $metadata
        )
        $created.Add($metadata)
    }

    if (-not (Test-Path -LiteralPath $brandPublic -PathType Container)) {
        New-Item -ItemType Directory -Path $brandPublic | Out-Null
        $created.Add($brandPublic)
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
    Push-Location $frontend
    try {
        Invoke-Native 'node' @('node_modules/@angular/cli/bin/ng.js', 'build', '--configuration', $configuration)
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
}
