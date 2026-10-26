#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$OutputDirectory = 'build/quality/pester',
    [ValidateSet('Bootstrap.Tests.ps1', 'Container.Tests.ps1', 'Operator.Tests.ps1', 'Compatibility.Tests.ps1', 'UbuntuQuality.Tests.ps1')]
    [string]$TestFile
)

$ErrorActionPreference = 'Stop'
$env:LZUG_IMAGE = if ($env:LZUG_IMAGE) {
    $env:LZUG_IMAGE
} elseif ($env:LZUG_QUALITY_APP_IMAGE) {
    $env:LZUG_QUALITY_APP_IMAGE
} else {
    'lzug-app:0.0.0-dev.local'
}
$env:LZUG_CONTRACT_IMAGE = if ($env:LZUG_CONTRACT_IMAGE) {
    $env:LZUG_CONTRACT_IMAGE
} elseif ($env:LZUG_QUALITY_CONTRACT_IMAGE) {
    $env:LZUG_QUALITY_CONTRACT_IMAGE
} else {
    'lzug-app:0.0.0-rc.0-contract'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$requirements = Join-Path $root 'tests/pester/requirements.psd1'
$moduleRoot = Join-Path $root '.tools/powershell'
$results = Join-Path $root $OutputDirectory
$pesterVersion = (Import-PowerShellDataFile $requirements).Pester

New-Item -ItemType Directory -Force -Path $moduleRoot, $results | Out-Null
$moduleManifest = Join-Path $moduleRoot "Pester/$pesterVersion/Pester.psd1"
if (-not (Test-Path -LiteralPath $moduleManifest)) {
    . (Join-Path $PSScriptRoot 'pester-bootstrap.ps1')
    Save-PinnedPesterModule -Version $pesterVersion -Path $moduleRoot
}
if (-not (Test-Path -LiteralPath $moduleManifest)) { throw "Pinned Pester module $pesterVersion could not be installed." }
Import-Module $moduleManifest -Force

$configuration = New-PesterConfiguration
$configuration.Run.Path = if ($TestFile) {
    $path = Join-Path $root 'tests/pester' $TestFile
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Pester test file does not exist: $TestFile"
    }
    $path
} else {
    Join-Path $root 'tests/pester'
}
$configuration.Run.Exit = $true
$configuration.TestResult.Enabled = $true
$configuration.TestResult.OutputPath = Join-Path $results 'pester.xml'
$configuration.TestResult.OutputFormat = 'NUnitXml'
$configuration.Output.Verbosity = 'Detailed'
Invoke-Pester -Configuration $configuration
