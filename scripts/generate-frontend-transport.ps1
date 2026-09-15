#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$arguments = @('run', '--locked', '--extra', 'dev', 'python', 'scripts/generate_frontend_transport.py')
if ($Check) { $arguments += '--check' }
Push-Location $root
try { & uv @arguments }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Frontend transport generation failed with exit code $LASTEXITCODE" }
