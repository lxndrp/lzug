#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$operatorRoot = Join-Path $repositoryRoot 'operator-cli'
$dist = Join-Path $operatorRoot 'dist'
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "lzug-operator-reproducibility-$([guid]::NewGuid())"
$generatedFiles = @(
    (Join-Path $operatorRoot '.goreleaser-build-metadata.json'),
    (Join-Path $operatorRoot '.goreleaser-license'),
    (Join-Path $operatorRoot '.goreleaser-third-party-notices.md')
)

function Invoke-Native {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

if (Test-Path -LiteralPath $dist) { throw 'operator-cli/dist must not exist before reproducibility verification.' }
foreach ($path in $generatedFiles) {
    if (Test-Path -LiteralPath $path) { throw "Generated GoReleaser input already exists: $path" }
}

New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    $revision = (& git -C $repositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to determine the Git revision.' }
    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $repositoryRoot 'backend/src'
    $version = (& python3 -m backend.version --revision $revision --field identity).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to determine the CLI build identity.' }

    Push-Location $operatorRoot
    try {
        Invoke-Native 'goreleaser' @('release', '--snapshot', '--clean')
        Move-Item -LiteralPath $dist -Destination (Join-Path $temporaryDirectory 'first')

        Invoke-Native 'goreleaser' @('release', '--snapshot', '--clean')
        Move-Item -LiteralPath $dist -Destination (Join-Path $temporaryDirectory 'second')

        $manifestPath = Join-Path $temporaryDirectory 'first/artifacts.json'
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $artifacts = @($manifest | Where-Object { $_.type -in @('Archive', 'Binary') })
        if ($artifacts.Count -eq 0) { throw 'GoReleaser manifest contains no archives or binaries.' }
        $secondManifest = Get-Content -LiteralPath (Join-Path $temporaryDirectory 'second/artifacts.json') -Raw | ConvertFrom-Json
        $secondArtifacts = @($secondManifest | Where-Object { $_.type -in @('Archive', 'Binary') })
        $firstSet = @($artifacts | ForEach-Object { "$($_.type)|$($_.path)|$($_.goos)|$($_.goarch)" } | Sort-Object)
        $secondSet = @($secondArtifacts | ForEach-Object { "$($_.type)|$($_.path)|$($_.goos)|$($_.goarch)" } | Sort-Object)
        if (Compare-Object $firstSet $secondSet) { throw 'GoReleaser artifact manifest changed between clean builds.' }
        foreach ($artifact in $artifacts) {
            $relativePath = ([string]$artifact.path) -replace '^dist[\\/]', ''
            if ([System.IO.Path]::IsPathRooted($relativePath) -or $relativePath -match '(^|[\\/])\.\.([\\/]|$)') {
                throw "Unsafe artifact path in GoReleaser manifest: $relativePath"
            }
            $first = Join-Path (Join-Path $temporaryDirectory 'first') $relativePath
            $second = Join-Path (Join-Path $temporaryDirectory 'second') $relativePath
            if (-not (Test-Path -LiteralPath $first -PathType Leaf) -or -not (Test-Path -LiteralPath $second -PathType Leaf)) {
                throw "Manifest artifact is missing from a clean build: $relativePath"
            }
            $firstHash = (Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash
            $secondHash = (Get-FileHash -LiteralPath $second -Algorithm SHA256).Hash
            if ($firstHash -ne $secondHash) { throw "CLI artifact differs between clean builds: $relativePath" }
        }

        $hostTarget = switch ("$([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)|$([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture)") {
            { $_ -match 'Darwin|macOS' -and $_ -match 'Arm64' } { 'darwin/arm64'; break }
            { $_ -match 'Darwin|macOS' -and $_ -match 'X64' } { 'darwin/amd64'; break }
            { $_ -match 'Linux' -and $_ -match 'X64' } { 'linux/amd64'; break }
            default { $null }
        }
        if ($hostTarget) {
            $goos, $goarch = $hostTarget.Split('/')
            $binary = $artifacts | Where-Object { $_.type -eq 'Binary' -and $_.goos -eq $goos -and $_.goarch -eq $goarch } | Select-Object -First 1
            if (-not $binary) { throw "GoReleaser manifest has no host binary for $hostTarget." }
            $binaryRelativePath = ([string]$binary.path) -replace '^dist[\\/]', ''
            $binaryPath = Join-Path (Join-Path $temporaryDirectory 'first') $binaryRelativePath
            $actual = (& $binaryPath --build-metadata | ConvertFrom-Json)
            if ($LASTEXITCODE -ne 0) { throw 'Host CLI metadata command failed.' }
            if ($actual.identity -ne $version -or $actual.revision -ne $revision -or $actual.release -ne $false -or $null -ne $actual.tag) {
                throw 'Host CLI metadata does not match the current snapshot build.'
            }
        }
        Write-Output 'CLI artifacts match across two clean builds.'
    } finally {
        Pop-Location
    }
} finally {
    if ($null -eq $previousPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    else { $env:PYTHONPATH = $previousPythonPath }
    if (Test-Path -LiteralPath $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
    foreach ($path in $generatedFiles) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
