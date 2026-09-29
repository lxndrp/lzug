#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('deploy', 'rollback')] [string]$Operation
)

$ErrorActionPreference = 'Stop'
$required = @(
    'AZURE_RESOURCE_GROUP', 'AZURE_CONTAINER_APP', 'DEMO_URL', 'APP_IMAGE',
    'SEED_IMAGE'
)

function Invoke-Native {
    param([Parameter(Mandatory)] [string]$Command, [Parameter(Mandatory)] [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Required demo deployment variable is missing: $name"
    }
}
if ($env:APP_IMAGE -notmatch '^ghcr\.io/lxndrp/lzug-demo-app@sha256:[0-9a-f]{64}$') { throw 'APP_IMAGE is not an immutable demo-app digest.' }
if ($env:SEED_IMAGE -notmatch '^ghcr\.io/lxndrp/lzug-demo-seed@sha256:[0-9a-f]{64}$') { throw 'SEED_IMAGE is not an immutable demo-seed digest.' }
if ($env:DEMO_URL -ne 'https://demo.lzug.repertoire.papaspyrou.name') { throw 'DEMO_URL is not the canonical demo origin.' }

if ($Operation -eq 'rollback' -and $env:GITHUB_REF -ne 'refs/heads/master') {
    throw 'Rollback may only be dispatched from master.'
}

$previous = Join-Path $env:RUNNER_TEMP 'demo-previous.json'
$query = "properties.template.{app:containers[?name=='lzug-demo-app'].image | [0],seed:initContainers[?name=='lzug-demo-seed'].image | [0]}"
Invoke-Native 'az' @('containerapp', 'show', '--name', $env:AZURE_CONTAINER_APP, '--resource-group', $env:AZURE_RESOURCE_GROUP, '--query', $query, '--output', 'json') | Set-Content -LiteralPath $previous
$suffix = "gh-$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)"
Invoke-Native 'az' @('containerapp', 'update', '--name', $env:AZURE_CONTAINER_APP, '--resource-group', $env:AZURE_RESOURCE_GROUP, '--revision-suffix', $suffix, '--set', "properties.template.containers[0].image=$($env:APP_IMAGE)", "properties.template.initContainers[0].image=$($env:SEED_IMAGE)")
if ($env:GITHUB_OUTPUT) { "revision_suffix=$suffix" | Add-Content -LiteralPath $env:GITHUB_OUTPUT }

for ($attempt = 1; $attempt -le 30; $attempt++) {
    $state = (& az containerapp revision list --name $env:AZURE_CONTAINER_APP --resource-group $env:AZURE_RESOURCE_GROUP --query "[?contains(name, '--$suffix')].properties.runningState | [0]" --output tsv).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to query the promoted Azure revision.' }
    if ($state -eq 'Running') { break }
    if ($state -in @('Failed', 'Degraded')) { throw "The promoted Azure revision is $state." }
    if ($attempt -eq 30) { throw 'The promoted Azure revision did not become ready.' }
    Start-Sleep -Seconds 10
}

$readiness = (& curl --fail --silent --show-error "$($env:DEMO_URL)/api/ready" | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $readiness.ready -ne $true) { throw 'Demo runtime readiness failed.' }

$previousState = Get-Content -Raw -LiteralPath $previous | ConvertFrom-Json
@(
    "### Demo $($Operation -eq 'rollback' ? 'rollback' : 'deployment') succeeded",
    "- URL: $($env:DEMO_URL)",
    "- App: ``$($env:APP_IMAGE)``",
    "- Seed: ``$($env:SEED_IMAGE)``",
    "- Azure revision suffix: ``$suffix``",
    "- Previous app digest: ``$($previousState.app)``",
    "- Previous seed digest: ``$($previousState.seed)``",
    '- Azure revision readiness and public runtime readiness passed.'
) | Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY
