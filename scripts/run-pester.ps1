#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [string]$OutputDirectory = 'build/quality/pester',
    [ValidateSet('Container.Tests.ps1', 'Operator.Tests.ps1', 'Compatibility.Tests.ps1', 'PublicationArtifact.Tests.ps1')]
    [string]$TestFile
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
