#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$OutputDirectory = 'build/quality/pester'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$requirements = Join-Path $root 'tests/pester/requirements.psd1'
$moduleRoot = Join-Path $root '.tools/powershell'
$results = Join-Path $root $OutputDirectory
$pesterVersion = (Import-PowerShellDataFile $requirements).Pester

New-Item -ItemType Directory -Force -Path $moduleRoot, $results | Out-Null
$moduleManifest = Join-Path $moduleRoot "Pester/$pesterVersion/Pester.psd1"
if (-not (Test-Path -LiteralPath $moduleManifest)) {
    Save-PSResource -Name Pester -Version $pesterVersion -Repository PSGallery -Path $moduleRoot -TrustRepository -Quiet
}
if (-not (Test-Path -LiteralPath $moduleManifest)) { throw "Pinned Pester module $pesterVersion could not be installed." }
Import-Module $moduleManifest -Force

$configuration = New-PesterConfiguration
$configuration.Run.Path = Join-Path $root 'tests/pester'
$configuration.Run.Exit = $true
$configuration.TestResult.Enabled = $true
$configuration.TestResult.OutputPath = Join-Path $results 'pester.xml'
$configuration.TestResult.OutputFormat = 'NUnitXml'
$configuration.Output.Verbosity = 'Detailed'
Invoke-Pester -Configuration $configuration
