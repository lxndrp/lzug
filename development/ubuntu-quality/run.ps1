Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'runner-contract.psm1') -Force

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
$builderName = $null
$buildxConfigPath = $null
$mutex = $null
$mutexAcquired = $false
$createdVolumes = [System.Collections.Generic.List[string]]::new()
$cleanupErrors = [System.Collections.Generic.List[string]]::new()
$qualityImages = $null
$resourceScope = $env:LZUG_DEVELOPMENT_RESOURCE_SCOPE
$persistentResources = -not [string]::IsNullOrWhiteSpace($resourceScope)
$imageBuilt = $false
$taskError = $null
$previousDockerHost = $env:DOCKER_HOST
$previousDockerContext = $env:DOCKER_CONTEXT
$previousBuildxConfig = $env:BUILDX_CONFIG
$dockerEnvironmentChanged = $false
$builderCleanupSucceeded = $true

try {
    $worktreeRoot = Get-NativeOutput -Command git -Arguments @('rev-parse', '--show-toplevel')
    $mutexIdentity = if ($persistentResources) { $resourceScope } else { $worktreeRoot }
    $mutexHash = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($mutexIdentity))
    ).ToLowerInvariant().Substring(0, 24)
    $mutex = [Threading.Mutex]::new($false, 'lzug-ubuntu-quality-local-docker')
    try {
        $mutexAcquired = $mutex.WaitOne(0)
        if (-not $mutexAcquired) {
            Write-Host 'Another Ubuntu quality run is active against the shared Docker engine; waiting for it to finish.'
            $mutexAcquired = $mutex.WaitOne()
        }
    }
    catch [Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is required for task quality:ubuntu.'
    }

    $dockerSocketPath = '/var/run/docker.sock'
    if (-not (Test-Path -LiteralPath $dockerSocketPath)) {
        throw "The local Docker socket is unavailable at $dockerSocketPath."
    }

    if ($env:DOCKER_CONTEXT) {
        $dockerContext = $env:DOCKER_CONTEXT
        $dockerEndpoint = Get-NativeOutput -Command docker -Arguments @(
            'context', 'inspect', $dockerContext, '--format', '{{.Endpoints.docker.Host}}'
        )
    }
    elseif ($env:DOCKER_HOST) {
        $dockerEndpoint = $env:DOCKER_HOST
    }
    else {
        $dockerContext = Get-NativeOutput -Command docker -Arguments @('context', 'show')
        $dockerEndpoint = Get-NativeOutput -Command docker -Arguments @(
            'context', 'inspect', $dockerContext, '--format', '{{.Endpoints.docker.Host}}'
        )
    }

    if (-not (Test-LzugLocalDockerEndpoint -Endpoint $dockerEndpoint -SocketPath $dockerSocketPath)) {
        throw "Docker endpoint '$dockerEndpoint' does not resolve to the local socket $dockerSocketPath. Select the local Docker context; this task bind-mounts that socket into the runner."
    }
    if ($persistentResources -and -not (Test-LzugWorktreeScope -Scope $resourceScope)) {
        throw "Invalid LZUG_DEVELOPMENT_RESOURCE_SCOPE: $resourceScope"
    }

    $buildxConfigPath = Join-Path $worktreeRoot '.codex/ubuntu-quality/buildx'
    New-Item -ItemType Directory -Force -Path $buildxConfigPath | Out-Null
    $dockerEnvironmentChanged = $true
    $env:BUILDX_CONFIG = $buildxConfigPath
    $env:DOCKER_HOST = 'unix:///var/run/docker.sock'
    Remove-Item Env:DOCKER_CONTEXT -ErrorAction SilentlyContinue

    Invoke-Docker -Arguments @('buildx', 'version') -Quiet
    Invoke-Docker -Arguments @('info') -Quiet

    if ($persistentResources) {
        $resourceLabel = "lzug-codex-$resourceScope"
        $resourcePrefix = "$resourceLabel-ubuntu-quality"
    }
    else {
        $resourcePrefix = "lzug-ubuntu-quality-$mutexHash"
        $resourceLabel = $resourcePrefix
    }
    $builderName = "$resourcePrefix-buildx"
    $qualityImages = Get-LzugQualityImageReferences -ResourcePrefix $resourcePrefix

    $staleContainerPrefix = "$resourcePrefix-run"
    $staleContainers = Get-NativeOutput -Command docker -Arguments @(
        'container', 'ls', '--all', '--format', '{{.ID}} {{.Names}}', '--filter', "name=$staleContainerPrefix"
    )
    foreach ($staleContainer in ($staleContainers -split '\r?\n')) {
        $containerDetails = $staleContainer.Trim() -split '\s+', 2
        if ($containerDetails.Count -eq 2) {
            $labelJson = Get-NativeOutput -Command docker -Arguments @(
                'container', 'inspect', '--format', '{{json .Config.Labels}}', $containerDetails[0]
            )
            $containerLabels = if ($labelJson -eq 'null') { @{} } else { ConvertFrom-Json -InputObject $labelJson -AsHashtable }
            if (Test-LzugRunnerContainerOwnership `
                    -ContainerName $containerDetails[1] `
                    -ContainerPrefix $staleContainerPrefix `
                    -ResourceLabel $resourceLabel `
                    -Labels $containerLabels) {
                Invoke-Docker -Arguments @('container', 'rm', '--force', $containerDetails[0]) -Quiet
            }
        }
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

    $builderNames = Get-NativeOutput -Command docker -Arguments @('buildx', 'ls', '--format', '{{.Name}}')
    $builderExists = $false
    foreach ($existingBuilder in ($builderNames -split '\r?\n')) {
        if (Test-LzugBuilderOwnership -BuilderName $existingBuilder.Trim() -ExpectedBuilderName $builderName) {
            $builderExists = $true
            break
        }
    }

    if ($builderExists -and -not $persistentResources) {
        Invoke-Docker -Arguments @('buildx', 'rm', '--force', $builderName) -Quiet
        $builderExists = $false
    }

    if (-not $builderExists) {
        Invoke-Docker -Arguments @(
            'buildx', 'create', '--name', $builderName, '--driver', 'docker-container', '--use', 'unix:///var/run/docker.sock'
        ) -Quiet
    }

    $buildArguments = @(
        'buildx', 'build',
        '--builder', $builderName,
        '--pull',
        '--load',
        '--build-arg', "PLAYWRIGHT_VERSION=$playwrightVersion",
        '--build-arg', "MISE_VERSION=$miseVersion",
        '--build-arg', "DOCKER_CLI_VERSION=$dockerCliVersion"
    )
    $buildArguments += @('--label', $resourceLabel)
    $buildArguments += @(
        '--tag', $image,
        '--file', 'development/ubuntu-quality/Dockerfile',
        '.'
    )
    Invoke-Docker -Arguments $buildArguments
    $imageBuilt = $true

    $buildxConfigGroupId = Get-NativeOutput -Command id -Arguments @('-g')
    if ($buildxConfigGroupId -notmatch '^\d+$') {
        throw "Cannot parse host group ID '$buildxConfigGroupId' for the worktree Buildx config."
    }
    Get-NativeOutput -Command chmod -Arguments @('-R', 'g+rwX', $buildxConfigPath) | Out-Null

    foreach ($cacheName in $cacheNames) {
        $volumeName = "$resourcePrefix-$cacheName"
        $volumeArguments = @('volume', 'create', '--name', $volumeName)
        $volumeArguments += @('--label', $resourceLabel)
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
        '--group-add', $buildxConfigGroupId,
        '--security-opt', "seccomp=$worktreeRoot/development/ubuntu-quality/seccomp-profile.json"
    )
    $runArguments += @('--label', $resourceLabel)
    if ($persistentResources) {
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
        '--env', "BUILDX_CONFIG=$buildxConfigPath",
        '--env', "BUILDX_BUILDER=$builderName",
        '--env', "LZUG_QUALITY_BUILDX_BUILDER=$builderName",
        '--env', 'GIT_OPTIONAL_LOCKS=0',
        '--env', "LZUG_QUALITY_APP_IMAGE=$($qualityImages.App)",
        '--env', "LZUG_QUALITY_CONTRACT_IMAGE=$($qualityImages.Contract)",
        '--env', "LZUG_QUALITY_DEMO_APP_IMAGE=$($qualityImages.DemoApp)",
        '--env', "LZUG_QUALITY_DEMO_SEED_IMAGE=$($qualityImages.DemoSeed)",
        '--env', "LZUG_QUALITY_RESOURCE_LABEL=$resourceLabel",
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
catch {
    $taskError = $_
}
finally {
    if ($containerName) {
        try {
            $containerRows = Get-NativeOutput -Command docker -Arguments @(
                'container', 'ls', '--all', '--format', '{{.ID}} {{.Names}}'
            )
            foreach ($containerRow in ($containerRows -split '\r?\n')) {
                $containerDetails = $containerRow.Trim() -split '\s+', 2
                if ($containerDetails.Count -eq 2 -and $containerDetails[1] -ceq $containerName) {
                    $labelJson = Get-NativeOutput -Command docker -Arguments @(
                        'container', 'inspect', '--format', '{{json .Config.Labels}}', $containerDetails[0]
                    )
                    $containerLabels = if ($labelJson -eq 'null') {
                        @{}
                    } else {
                        ConvertFrom-Json -InputObject $labelJson -AsHashtable
                    }
                    if (Test-LzugRunnerContainerOwnership `
                            -ContainerName $containerDetails[1] `
                            -ContainerPrefix "$resourcePrefix-run" `
                            -ResourceLabel $resourceLabel `
                            -Labels $containerLabels) {
                        Invoke-Docker -Arguments @('container', 'rm', '--force', $containerDetails[0]) -Quiet
                    }
                }
            }
        }
        catch {
            $cleanupErrors.Add("runner container cleanup failed: $($_.Exception.Message)") | Out-Null
        }
    }

    if (-not $persistentResources) {
        foreach ($volumeName in $createdVolumes) {
            try {
                Invoke-Docker -Arguments @('volume', 'rm', $volumeName) -Quiet
            }
            catch {
                $cleanupErrors.Add("volume '$volumeName' cleanup failed: $($_.Exception.Message)") | Out-Null
            }
        }

        if ($imageBuilt -and $image) {
            try {
                Invoke-Docker -Arguments @('image', 'rm', $image) -Quiet
            }
            catch {
                $cleanupErrors.Add("runner image '$image' cleanup failed: $($_.Exception.Message)") | Out-Null
            }
        }

        if ($qualityImages) {
            try {
                $existingImages = Get-NativeOutput -Command docker -Arguments @(
                    'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}'
                )
                foreach ($qualityImage in $qualityImages.Values) {
                    if (($existingImages -split '\r?\n') -ccontains $qualityImage) {
                        Invoke-Docker -Arguments @('image', 'rm', $qualityImage) -Quiet
                    }
                }
            }
            catch {
                $cleanupErrors.Add("quality image cleanup failed: $($_.Exception.Message)") | Out-Null
            }
        }

        if ($builderName) {
            try {
                $existingBuilders = Get-NativeOutput -Command docker -Arguments @(
                    'buildx', 'ls', '--format', '{{.Name}}'
                )
                foreach ($existingBuilder in ($existingBuilders -split '\r?\n')) {
                    if (Test-LzugBuilderOwnership -BuilderName $existingBuilder.Trim() -ExpectedBuilderName $builderName) {
                        Invoke-Docker -Arguments @('buildx', 'rm', '--force', $builderName) -Quiet
                        break
                    }
                }
            }
            catch {
                $builderCleanupSucceeded = $false
                $cleanupErrors.Add("Buildx builder '$builderName' cleanup failed: $($_.Exception.Message)") | Out-Null
            }
        }

        if ($buildxConfigPath -and $builderCleanupSucceeded -and
            (Test-Path -LiteralPath $buildxConfigPath -PathType Container)) {
            try {
                Remove-Item -LiteralPath $buildxConfigPath -Recurse -Force
            }
            catch {
                $cleanupErrors.Add("Buildx config '$buildxConfigPath' cleanup failed: $($_.Exception.Message)") | Out-Null
            }
        }
    }

    if ($mutex -and $mutexAcquired) {
        try {
            $mutex.ReleaseMutex()
        }
        catch {
            $cleanupErrors.Add("runner lock release failed: $($_.Exception.Message)") | Out-Null
        }
    }
    if ($mutex) {
        try {
            $mutex.Dispose()
        }
        catch {
            $cleanupErrors.Add("runner lock disposal failed: $($_.Exception.Message)") | Out-Null
        }
    }

    if ($dockerEnvironmentChanged) {
        if ($null -eq $previousDockerHost) {
            Remove-Item Env:DOCKER_HOST -ErrorAction SilentlyContinue
        } else {
            $env:DOCKER_HOST = $previousDockerHost
        }
        if ($null -eq $previousDockerContext) {
            Remove-Item Env:DOCKER_CONTEXT -ErrorAction SilentlyContinue
        } else {
            $env:DOCKER_CONTEXT = $previousDockerContext
        }
        if ($null -eq $previousBuildxConfig) {
            Remove-Item Env:BUILDX_CONFIG -ErrorAction SilentlyContinue
        } else {
            $env:BUILDX_CONFIG = $previousBuildxConfig
        }
    }

    try {
        Pop-Location
    }
    catch {
        $cleanupErrors.Add("working directory restore failed: $($_.Exception.Message)") | Out-Null
    }
}

Complete-LzugRunnerOutcome -TaskError $taskError -CleanupErrors $cleanupErrors.ToArray()
