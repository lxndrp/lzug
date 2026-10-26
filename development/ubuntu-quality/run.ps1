Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-NativeOutput {
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $output = & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }

    return ($output -join [Environment]::NewLine).Trim()
}

function Invoke-Docker {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [switch]$Quiet
    )

    if ($Quiet) {
        & docker @Arguments *> $null
    }
    else {
        & docker @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repositoryRoot

$containerName = $null
$image = $null
$mutex = $null
$mutexAcquired = $false
$createdVolumes = [System.Collections.Generic.List[string]]::new()
$resourceScope = $env:LZUG_DEVELOPMENT_RESOURCE_SCOPE
$persistentResources = -not [string]::IsNullOrWhiteSpace($resourceScope)
$imageBuilt = $false

try {
    $worktreeRoot = Get-NativeOutput -Command git -Arguments @('rev-parse', '--show-toplevel')
    $mutexIdentity = if ($persistentResources) { $resourceScope } else { $worktreeRoot }
    $mutexHash = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($mutexIdentity))
    ).ToLowerInvariant().Substring(0, 24)
    $mutex = [Threading.Mutex]::new($false, "lzug-ubuntu-quality-$mutexHash")
    try {
        $mutexAcquired = $mutex.WaitOne(0)
        if (-not $mutexAcquired) {
            Write-Host 'Another Ubuntu quality run is active for this worktree; waiting for it to finish.'
            $mutexAcquired = $mutex.WaitOne()
        }
    }
    catch [Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is required for task quality:ubuntu.'
    }

    Invoke-Docker -Arguments @('info') -Quiet
    if (-not (Test-Path -LiteralPath '/var/run/docker.sock')) {
        throw 'The local Docker socket is unavailable at /var/run/docker.sock.'
    }

    $gitCommonDirectory = Get-NativeOutput -Command git -Arguments @(
        'rev-parse', '--path-format=absolute', '--git-common-dir'
    )

    $lock = Get-Content -Raw frontend/package-lock.json | ConvertFrom-Json -AsHashtable
    $playwrightVersion = $lock.packages['node_modules/@playwright/test'].version
    if ([string]::IsNullOrWhiteSpace($playwrightVersion)) {
        throw 'The Playwright test version is missing from frontend/package-lock.json.'
    }

    $miseOutput = Get-NativeOutput -Command mise -Arguments @('--version')
    if ($miseOutput -notmatch '^(?:mise\s+)?(?<Version>\S+)') {
        throw "Cannot parse mise version from '$miseOutput'."
    }
    $miseVersion = $Matches.Version

    $dockerOutput = Get-NativeOutput -Command docker -Arguments @('--version')
    if ($dockerOutput -notmatch '^Docker version (?<Version>[^,]+),') {
        throw "Cannot parse Docker CLI version from '$dockerOutput'."
    }
    $dockerCliVersion = $Matches.Version

    if ($persistentResources) {
        if ($resourceScope -notmatch '^[a-z0-9-]+$') {
            throw "Invalid LZUG_DEVELOPMENT_RESOURCE_SCOPE: $resourceScope"
        }

        $resourceLabel = "lzug-codex-$resourceScope"
        $resourcePrefix = "$resourceLabel-ubuntu-quality"
    }
    else {
        $resourceLabel = $null
        $resourcePrefix = "lzug-ubuntu-quality-$PID"
    }

    $fingerprintInput = @(
        (Get-Content -Raw Taskfile.yml)
        (Get-Content -Raw development/ubuntu-quality/Dockerfile)
        (Get-Content -Raw development/ubuntu-quality/seccomp-profile.json)
        $playwrightVersion
        $miseVersion
        $dockerCliVersion
    ) -join "`n"
    $fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintInput)
    $fingerprint = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData($fingerprintBytes)
    ).ToLowerInvariant().Substring(0, 40)

    $image = "${resourcePrefix}:$fingerprint"
    $containerName = "$resourcePrefix-run-$PID"
    $cacheNames = @(
        'mise-data',
        'mise-cache',
        'uv-cache',
        'npm-cache',
        'go-mod',
        'go-build',
        'venv',
        'frontend-node-modules'
    )

    $buildArguments = @(
        'build',
        '--pull',
        '--build-arg', "PLAYWRIGHT_VERSION=$playwrightVersion",
        '--build-arg', "MISE_VERSION=$miseVersion",
        '--build-arg', "DOCKER_CLI_VERSION=$dockerCliVersion"
    )
    if ($resourceLabel) {
        $buildArguments += @('--label', $resourceLabel)
    }
    $buildArguments += @(
        '--tag', $image,
        '--file', 'development/ubuntu-quality/Dockerfile',
        '.'
    )
    Invoke-Docker -Arguments $buildArguments
    $imageBuilt = $true

    foreach ($cacheName in $cacheNames) {
        $volumeName = "$resourcePrefix-$cacheName"
        $volumeArguments = @('volume', 'create', '--name', $volumeName)
        if ($resourceLabel) {
            $volumeArguments += @('--label', $resourceLabel)
        }
        Invoke-Docker -Arguments $volumeArguments -Quiet
        $createdVolumes.Add($volumeName) | Out-Null

        Invoke-Docker -Arguments @(
            'run', '--rm', '--user', '0:0',
            '--mount', "type=volume,source=$volumeName,target=/cache",
            '--entrypoint', '/bin/chown',
            $image, '1001:1001', '/cache'
        ) -Quiet
    }

    $socketGroupId = Get-NativeOutput -Command docker -Arguments @(
        'run', '--rm',
        '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
        '--entrypoint', 'stat',
        $image, '-c', '%g', '/var/run/docker.sock'
    )
    Invoke-Docker -Arguments @(
        'run', '--rm', '--user', '1001:1001', '--group-add', $socketGroupId,
        '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
        '--entrypoint', 'docker', $image, 'info'
    ) -Quiet

    $runArguments = @(
        'run', '--rm', '--name', $containerName,
        '--init', '--shm-size=1g', '--user', '1001:1001',
        '--group-add', $socketGroupId,
        '--security-opt', "seccomp=$worktreeRoot/development/ubuntu-quality/seccomp-profile.json"
    )
    if ($resourceLabel) {
        $runArguments += @('--label', $resourceLabel)
        $runArguments += @('--env', "LZUG_DEVELOPMENT_RESOURCE_SCOPE=$resourceScope")
    }
    $runArguments += @(
        '--mount', "type=bind,source=$worktreeRoot,target=$worktreeRoot",
        '--mount', "type=bind,source=$gitCommonDirectory,target=$gitCommonDirectory,readonly",
        '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
        '--mount', "type=volume,source=$resourcePrefix-mise-data,target=/home/pwuser/.local/share/mise,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-mise-cache,target=/home/pwuser/.cache/mise,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-uv-cache,target=/home/pwuser/.cache/uv,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-npm-cache,target=/home/pwuser/.cache/npm,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-go-mod,target=/home/pwuser/go/pkg/mod,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-go-build,target=/home/pwuser/.cache/go-build,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-venv,target=$worktreeRoot/.venv,volume-nocopy",
        '--mount', "type=volume,source=$resourcePrefix-frontend-node-modules,target=$worktreeRoot/frontend/node_modules,volume-nocopy",
        '--workdir', $worktreeRoot,
        '--env', 'CI=true',
        '--env', 'DOCKER_BUILDKIT=1',
        '--env', 'DOCKER_HOST=unix:///var/run/docker.sock',
        '--env', 'GIT_OPTIONAL_LOCKS=0',
        $image,
        '/bin/sh', '-eu', '-c', @'
git config --global --add safe.directory "$PWD"
mise install
mise exec -- task setup
mise exec -- task doctor
mise exec -- task doctor:playwright
mise exec -- task --concurrency=4 quality
'@
    )
    Invoke-Docker -Arguments $runArguments
}
finally {
    if ($containerName) {
        try {
            Invoke-Docker -Arguments @('rm', '-f', $containerName) -Quiet
        }
        catch {
            # The container may already have been removed by --rm.
        }
    }

    if (-not $persistentResources) {
        foreach ($volumeName in $createdVolumes) {
            try {
                Invoke-Docker -Arguments @('volume', 'rm', $volumeName) -Quiet
            }
            catch {
                # Preserve the original task failure if Docker cannot remove a cache.
            }
        }

        if ($imageBuilt -and $image) {
            try {
                Invoke-Docker -Arguments @('image', 'rm', $image) -Quiet
            }
            catch {
                # Preserve the original task failure if Docker cannot remove the runner image.
            }
        }
    }

    if ($mutex -and $mutexAcquired) {
        $mutex.ReleaseMutex()
    }
    if ($mutex) {
        $mutex.Dispose()
    }

    Pop-Location
}
