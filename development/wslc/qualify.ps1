Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$outputDirectory = Join-Path $env:RUNNER_TEMP 'wslc-qualification'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
Push-Location $repositoryRoot

$evidence = [ordered]@{
    repositoryRevision = $null
    windows = $null
    wslVersion = $null
    wslcVersion = $null
    architecture = $null
    processors = $null
    memoryBytes = $null
    resourceScope = $null
    buildDurationsSeconds = [ordered]@{}
    artifacts = [ordered]@{}
    runtime = [ordered]@{}
    cleanup = [ordered]@{ containers = @(); volumes = @(); images = @(); cacheRetained = $true }
    blockers = [System.Collections.Generic.List[string]]::new()
    failure = $null
}
$ownedContainers = [System.Collections.Generic.List[string]]::new()
$ownedVolumes = [System.Collections.Generic.List[string]]::new()
$ownedImages = [System.Collections.Generic.List[string]]::new()
$badBuildDirectory = $null
$failure = $null
$cleanupFailures = [System.Collections.Generic.List[string]]::new()

function Invoke-External {
    param(
        [Parameter(Mandatory)] [string] $FilePath,
        [Parameter(Mandatory)] [string[]] $Arguments,
        [switch] $AllowFailure
    )

    Write-Host "> $FilePath $($Arguments -join ' ')"
    $lines = @(& $FilePath @Arguments 2>&1 | ForEach-Object { "$_" })
    $exitCode = $LASTEXITCODE
    $text = $lines -join "`n"
    if ($text) { Write-Host $text }
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "$FilePath failed with exit code $exitCode`: $text"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Text = $text }
}

function Invoke-Wslc {
    param([Parameter(Mandatory)] [string[]] $Arguments, [switch] $AllowFailure)
    Invoke-External -FilePath $script:wslcPath -Arguments $Arguments -AllowFailure:$AllowFailure
}

function Build-WslcImage {
    param([Parameter(Mandatory)] [string] $Name, [Parameter(Mandatory)] [string[]] $Arguments)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Invoke-Wslc -Arguments $Arguments | Out-Null
    $timer.Stop()
    $evidence.buildDurationsSeconds[$Name] = [math]::Round($timer.Elapsed.TotalSeconds, 2)
    Write-Host "$Name duration=$($evidence.buildDurationsSeconds[$Name])s"
}

function Get-WslcImageInfo {
    param([Parameter(Mandatory)] [string] $Image)
    $result = Invoke-Wslc -Arguments @('image', 'inspect', '--format', 'json', $Image)
    $parsed = $result.Text | ConvertFrom-Json -AsHashtable
    if ($parsed -is [array]) { $parsed = $parsed[0] }
    if ($null -eq $parsed) { throw "wslc returned no image metadata for $Image." }
    return $parsed
}

function Get-WslcContainerInfo {
    param([Parameter(Mandatory)] [string] $Container)
    $result = Invoke-Wslc -Arguments @('container', 'inspect', '--format', 'json', $Container)
    $parsed = $result.Text | ConvertFrom-Json -AsHashtable
    if ($parsed -is [array]) { $parsed = $parsed[0] }
    if ($null -eq $parsed) { throw "wslc returned no container metadata for $Container." }
    return $parsed
}

function Get-WslcVolumeInfo {
    param([Parameter(Mandatory)] [string] $Volume)
    $result = Invoke-Wslc -Arguments @('volume', 'inspect', '--format', 'json', $Volume)
    $parsed = $result.Text | ConvertFrom-Json -AsHashtable
    if ($parsed -is [array]) { $parsed = $parsed[0] }
    if ($null -eq $parsed) { throw "wslc returned no volume metadata for $Volume." }
    return $parsed
}

function Save-And-ScanImage {
    param([Parameter(Mandatory)] [string] $Name, [Parameter(Mandatory)] [string] $Image)
    $archive = Join-Path $outputDirectory "$Name.tar"
    $sbom = Join-Path $outputDirectory "$Name.sbom.cdx.json"
    Invoke-Wslc -Arguments @('image', 'save', '--output', $archive, $Image) | Out-Null
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
        throw "wslc did not save the $Name image archive at $archive."
    }
    $digest = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Invoke-External -FilePath $script:syftPath -Arguments @(
        'scan', '--config', (Join-Path $repositoryRoot '.syft.yaml'),
        "docker-archive:$archive", '--output', "cyclonedx-json@1.6=$sbom"
    ) | Out-Null
    $sbomDocument = Get-Content -LiteralPath $sbom -Raw | ConvertFrom-Json -AsHashtable
    if ($sbomDocument.bomFormat -ne 'CycloneDX' -or @($sbomDocument.components).Count -eq 0) {
        throw "Syft did not produce a populated CycloneDX SBOM for $Name."
    }
    $artifact = $evidence.artifacts[$Name]
    $artifact.archive = [IO.Path]::GetFileName($archive)
    $artifact.archiveBytes = (Get-Item -LiteralPath $archive).Length
    $artifact.archiveSha256 = $digest
    $artifact.sbom = [IO.Path]::GetFileName($sbom)
    $artifact.sbomComponents = @($sbomDocument.components).Count
}

function Wait-ForHttp {
    param([Parameter(Mandatory)] [string] $Url, [int] $TimeoutSeconds = 60)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-RestMethod -Uri $Url -TimeoutSec 3
            return $response
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    $logResult = Invoke-Wslc -Arguments @('logs', $script:currentContainer) -AllowFailure
    throw "Runtime did not answer $Url within ${TimeoutSeconds}s. Container logs: $($logResult.Text)"
}

function Start-WslcApp {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Image,
        [Parameter(Mandatory)] [string] $Volume,
        [Parameter(Mandatory)] [int] $HostPort,
        [switch] $ReadOnly
    )
    $script:currentContainer = $Name
    $arguments = @(
        'run', '--detach', '--name', $Name,
        '--label', "$script:resourceLabel=$script:runId",
        '--publish', "127.0.0.1:$HostPort`:8000",
        '--env', 'LZUG_HTTPS_ONLY=false',
        '--tmpfs', '/tmp',
        '--tmpfs', '/run/lzug-admin:rw,nosuid,nodev,uid=10001,gid=10001,mode=0770',
        '--mount', "type=volume,source=$Volume,target=/data"
    )
    if ($ReadOnly) { $arguments += '--read-only' }
    if ($script:runHelp -match '--cap-drop') { $arguments += @('--cap-drop', 'ALL') }
    if ($script:runHelp -match '--security-opt') {
        $arguments += @('--security-opt', 'no-new-privileges:true')
    }
    $arguments += $Image
    Invoke-Wslc -Arguments $arguments | Out-Null
    $ownedContainers.Add($Name)
}

function Test-LzugApiReady {
    param([Parameter(Mandatory)] [string] $Url)
    $lifecycle = Wait-ForHttp -Url "$Url/api/lifecycle"
    if ($lifecycle.state -ne 'ready' -or $lifecycle.ready -ne $true) {
        throw "Product lifecycle did not become ready: $($lifecycle | ConvertTo-Json -Compress)"
    }
}

try {
    $wslcCommand = Get-Command wslc.exe -ErrorAction SilentlyContinue
    if ($null -eq $wslcCommand) { throw 'wslc.exe is missing; install/update WSL to a version that includes wslc.' }
    $script:wslcPath = $wslcCommand.Source
    $script:syftPath = $env:SYFT_BINARY
    if ([string]::IsNullOrWhiteSpace($script:syftPath)) {
        $syftCommand = Get-Command syft -ErrorAction Stop
        $script:syftPath = $syftCommand.Source
    }

    $runId = $env:GITHUB_RUN_ID
    $runAttempt = $env:GITHUB_RUN_ATTEMPT
    if ([string]::IsNullOrWhiteSpace($runId) -or [string]::IsNullOrWhiteSpace($runAttempt)) {
        throw 'GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT are required for isolated resource names.'
    }
    $script:runId = "$runId-$runAttempt"
    $script:resourcePrefix = "lzug-ci-$($script:runId)"
    $script:resourceLabel = 'lzug-ci-run'

    Write-Host 'Updating the hosted WSL runtime from the official GitHub release channel.'
    Invoke-External -FilePath 'wsl.exe' -Arguments @('--update', '--web-download') | Out-Null
    Invoke-External -FilePath 'wsl.exe' -Arguments @('--shutdown') | Out-Null

    $os = Get-CimInstance Win32_OperatingSystem
    $computer = Get-CimInstance Win32_ComputerSystem
    $processorArchitecture = $env:PROCESSOR_ARCHITECTURE
    $expectedImageArchitecture = switch ($processorArchitecture) {
        'AMD64' { 'amd64' }
        'ARM64' { 'arm64' }
        default { throw "Unsupported Windows runner architecture: $processorArchitecture" }
    }
    $evidence.windows = $os.Version
    $evidence.architecture = $expectedImageArchitecture
    $evidence.processors = [Environment]::ProcessorCount
    $evidence.memoryBytes = $computer.TotalPhysicalMemory
    $evidence.resourceScope = "$script:resourcePrefix-*"
    Write-Host "Windows=$($os.Version) Architecture=$processorArchitecture CPUs=$($evidence.processors) MemoryBytes=$($evidence.memoryBytes)"

    $wslOutput = Invoke-External -FilePath 'wsl.exe' -Arguments @('--version')
    $wslText = $wslOutput.Text -replace "`0", ''
    $versionMatch = [regex]::Match($wslText, '(?m)^WSL version:\s*(\d+\.\d+\.\d+(?:\.\d+)?)')
    if (-not $versionMatch.Success) { throw 'Could not identify the installed WSL version.' }
    $wslVersion = [Version]$versionMatch.Groups[1].Value
    if ($wslVersion -lt [Version]'2.9.3') { throw "WSL $wslVersion is older than the wslc minimum 2.9.3." }
    $evidence.wslVersion = $wslVersion.ToString()

    $wslcVersionOutput = Invoke-Wslc -Arguments @('version')
    $wslcVersionMatch = [regex]::Match($wslcVersionOutput.Text, '(?i)wslc\s+(\d+\.\d+\.\d+(?:\.\d+)?)')
    if (-not $wslcVersionMatch.Success) { throw 'Could not identify the installed wslc version.' }
    $wslcVersion = [Version]$wslcVersionMatch.Groups[1].Value
    $evidence.wslcVersion = $wslcVersion.ToString()
    Invoke-Wslc -Arguments @('info') | Out-Null
    $script:runHelp = (Invoke-Wslc -Arguments @('run', '--help')).Text
    Invoke-Wslc -Arguments @('build', '--help') | Out-Null
    Invoke-Wslc -Arguments @('volume', 'create', '--help') | Out-Null
    Invoke-Wslc -Arguments @('container', 'inspect', '--help') | Out-Null
    Invoke-Wslc -Arguments @('image', 'inspect', '--help') | Out-Null
    Invoke-Wslc -Arguments @('image', 'save', '--help') | Out-Null
    Invoke-Wslc -Arguments @('container', 'stop', '--help') | Out-Null
    Invoke-Wslc -Arguments @('container', 'start', '--help') | Out-Null

    $capabilities = [ordered]@{
        readOnlyRootFilesystem = $script:runHelp -match '--read-only'
        dropCapabilities = $script:runHelp -match '--cap-drop'
        noNewPrivileges = $script:runHelp -match '--security-opt'
        namedVolumes = $script:runHelp -match '--mount'
        publishedPorts = $script:runHelp -match '--publish'
        labels = $script:runHelp -match '--label'
    }
    $evidence.runtime.capabilities = $capabilities
    foreach ($requirement in @(
        @{ Name = 'read-only root filesystem'; Available = $capabilities.readOnlyRootFilesystem },
        @{ Name = 'capability dropping'; Available = $capabilities.dropCapabilities },
        @{ Name = 'no-new-privileges security option'; Available = $capabilities.noNewPrivileges },
        @{ Name = 'named volumes'; Available = $capabilities.namedVolumes },
        @{ Name = 'published ports'; Available = $capabilities.publishedPorts },
        @{ Name = 'resource labels'; Available = $capabilities.labels }
    )) {
        if (-not $requirement.Available) {
            $evidence.blockers.Add("wslc $wslcVersion does not expose $($requirement.Name) in 'wslc run --help'.")
        }
    }

    $helloTimer = [Diagnostics.Stopwatch]::StartNew()
    $helloResult = Invoke-Wslc -Arguments @(
        'run', '--rm', '--label', "$script:resourceLabel=$script:runId", 'hello-world'
    )
    $helloTimer.Stop()
    if ($helloResult.Text -notmatch 'Hello from Docker') {
        throw "wslc hello-world did not produce its expected output: $($helloResult.Text)"
    }
    $evidence.runtime.helloWorldSeconds = [math]::Round($helloTimer.Elapsed.TotalSeconds, 2)

    $revisionResult = Invoke-External -FilePath 'git.exe' -Arguments @('rev-parse', 'HEAD')
    $revision = $revisionResult.Text.Trim()
    if ($revision -notmatch '^[0-9a-f]{40}$') { throw "Invalid checked-out revision: $revision" }
    $evidence.repositoryRevision = $revision
    $shortRevision = $revision.Substring(0, 7)
    $productIdentity = (Invoke-External -FilePath 'python.exe' -Arguments @(
        'backend/src/backend/version.py', '--revision', $revision, '--field', 'identity'
    )).Text.Trim()
    $demoTag = "snapshot/v0.2.0-SNAPSHOT.$shortRevision"
    $demoIdentity = (Invoke-External -FilePath 'python.exe' -Arguments @(
        'backend/src/backend/version.py', '--revision', $revision, '--tag', $demoTag,
        '--allow-demo-snapshot', '--field', 'identity'
    )).Text.Trim()

    $productImage = "$script:resourcePrefix-product:local"
    $seedImage = "$script:resourcePrefix-demo-seed:local"
    $demoImage = "$script:resourcePrefix-demo-app:local"
    $buildPrefix = @('--label', "$script:resourceLabel=$script:runId")
    $productBuild = $buildPrefix + @(
        '--no-cache', '--build-arg', "BUILD_IDENTITY=$productIdentity",
        '--build-arg', "VCS_REF=$revision", '--file', 'packaging/product/Dockerfile',
        '--tag', $productImage, '.'
    )
    $seedBuild = $buildPrefix + @(
        '--no-cache', '--build-arg', "PRODUCT_TAG=$demoTag",
        '--build-arg', "VCS_REF=$revision", '--file', 'packaging/demo/Dockerfile.seed',
        '--tag', $seedImage, '.'
    )
    Build-WslcImage -Name 'product-cold' -Arguments (@('build') + $productBuild)
    $ownedImages.Add($productImage)
    Build-WslcImage -Name 'demo-seed-cold' -Arguments (@('build') + $seedBuild)
    $ownedImages.Add($seedImage)

    $seedManifestOutput = Invoke-Wslc -Arguments @(
        'run', '--rm', '--entrypoint', 'python', $seedImage, '-c',
        "import json; print(json.load(open('/opt/lzug-demo/seed/manifest.json'))['seed_revision'])"
    )
    $seedRevision = ($seedManifestOutput.Text -split "`n" | Where-Object { $_ -match '^[0-9a-f]{64}$' } | Select-Object -Last 1)
    if (-not $seedRevision) { throw 'Could not extract the seed revision from the built seed image.' }

    $demoBuild = $buildPrefix + @(
        '--no-cache', '--build-arg', "BUILD_IDENTITY=$demoIdentity",
        '--build-arg', "PRODUCT_TAG=$demoTag", '--build-arg', "VCS_REF=$revision",
        '--build-arg', "SEED_REVISION=$seedRevision", '--file', 'packaging/demo/Dockerfile',
        '--tag', $demoImage, '.'
    )
    Build-WslcImage -Name 'demo-app-cold' -Arguments (@('build') + $demoBuild)
    $ownedImages.Add($demoImage)
    Build-WslcImage -Name 'product-cached' -Arguments (@('build') + $productBuild | Where-Object { $_ -ne '--no-cache' })
    Build-WslcImage -Name 'demo-seed-cached' -Arguments (@('build') + $seedBuild | Where-Object { $_ -ne '--no-cache' })
    Build-WslcImage -Name 'demo-app-cached' -Arguments (@('build') + $demoBuild | Where-Object { $_ -ne '--no-cache' })

    foreach ($imageSpec in @(
        @{ Name = 'product'; Tag = $productImage; Identity = $productIdentity; Revision = $revision },
        @{ Name = 'demo-seed'; Tag = $seedImage; Identity = $demoTag; Revision = $revision },
        @{ Name = 'demo-app'; Tag = $demoImage; Identity = $demoIdentity; Revision = $revision }
    )) {
        $info = Get-WslcImageInfo -Image $imageSpec.Tag
        if ($info.Os -ne 'linux' -or $info.Architecture -ne $expectedImageArchitecture) {
            throw "Unexpected $($imageSpec.Name) image platform: $($info.Os)/$($info.Architecture); expected linux/$expectedImageArchitecture."
        }
        $labels = $info.Config.Labels
        if ($labels[$script:resourceLabel] -ne $script:runId) {
            throw "Resource label is missing from image $($imageSpec.Tag)."
        }
        if ($imageSpec.Name -ne 'demo-seed') {
            $expectedIdentity = if ($imageSpec.Name -eq 'product') { $productIdentity } else { $demoIdentity }
            if ($labels['org.opencontainers.image.version'] -ne $expectedIdentity -or
                $labels['org.opencontainers.image.revision'] -ne $revision) {
                throw "Build identity or revision labels do not match for $($imageSpec.Name)."
            }
        } elseif ($labels['org.opencontainers.image.revision'] -ne $revision -or
            $labels['org.opencontainers.image.version'] -ne $demoTag) {
            throw 'Demo seed build identity or revision labels do not match.'
        }
        $evidence.artifacts[$imageSpec.Name] = [ordered]@{
            image = $imageSpec.Tag
            os = $info.Os
            architecture = $info.Architecture
            revision = $revision
            identity = $labels['org.opencontainers.image.version']
            seedRevision = if ($imageSpec.Name -eq 'demo-seed') { $seedRevision } else { $null }
        }
    }

    Save-And-ScanImage -Name 'product' -Image $productImage
    Save-And-ScanImage -Name 'demo-seed' -Image $seedImage
    Save-And-ScanImage -Name 'demo-app' -Image $demoImage

    $productVolume = "$script:resourcePrefix-product-data"
    $demoVolume = "$script:resourcePrefix-demo-data"
    foreach ($volume in @($productVolume, $demoVolume)) {
        Invoke-Wslc -Arguments @('volume', 'create', '--label', "$script:resourceLabel=$script:runId", $volume) | Out-Null
        $ownedVolumes.Add($volume)
        $volumeInfo = Get-WslcVolumeInfo -Volume $volume
        if ($volumeInfo.Labels[$script:resourceLabel] -ne $script:runId) {
            throw "Resource label is missing from volume $volume."
        }
    }
    Start-WslcApp -Name "$script:resourcePrefix-product-app" -Image $productImage -Volume $productVolume -HostPort 18080 -ReadOnly:$capabilities.readOnlyRootFilesystem
    Test-LzugApiReady -Url 'http://127.0.0.1:18080'
    $productHealth = Wait-ForHttp -Url 'http://127.0.0.1:18080/api/health'
    if ($productHealth.revision -ne $revision -or $productHealth.version -ne $productIdentity) {
        throw "Product health metadata does not match the built revision: $($productHealth | ConvertTo-Json -Compress)"
    }
    $adminStatusText = Invoke-Wslc -Arguments @(
        'exec', '--user', '10001:10001', "$script:resourcePrefix-product-app",
        'lzug-admin', '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json', 'system', 'status'
    )
    $adminStatus = $adminStatusText.Text | ConvertFrom-Json
    if (-not $adminStatus.ok -or $adminStatus.result.socket.state -ne 'listening') {
        throw "Admin CLI could not use the runtime socket: $($adminStatusText.Text)"
    }
    $socketCheck = "import os,stat; s=os.stat('/run/lzug-admin/admin.sock'); assert stat.S_ISSOCK(s.st_mode); assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(10001,10001,0o660)"
    Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-product-app", 'python', '-c', $socketCheck) | Out-Null
    $uidCheck = "import os; assert (os.geteuid(), os.getegid())==(10001,10001)"
    Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-product-app", 'python', '-c', $uidCheck) | Out-Null
    $productContainerInfo = Get-WslcContainerInfo -Container "$script:resourcePrefix-product-app"
    $hostConfig = $productContainerInfo.HostConfig
    if ($productContainerInfo.Config.Labels[$script:resourceLabel] -ne $script:runId) {
        throw 'Resource label is missing from the product container.'
    }
    if ($productContainerInfo.Config.User -ne '10001:10001' -or $hostConfig.Privileged -eq $true) {
        throw 'Product container does not preserve the non-root, non-privileged runtime contract.'
    }
    if ($capabilities.readOnlyRootFilesystem -and $hostConfig.ReadonlyRootfs -ne $true) {
        throw 'wslc accepted --read-only but did not report a read-only root filesystem.'
    }
    if ($capabilities.dropCapabilities -and $hostConfig.CapDrop -notcontains 'ALL') {
        throw 'wslc accepted --cap-drop ALL but did not report it in the container configuration.'
    }
    if ($capabilities.noNewPrivileges -and $hostConfig.SecurityOpt -notcontains 'no-new-privileges:true') {
        throw 'wslc accepted the no-new-privileges option but did not report it in the container configuration.'
    }
    $hostAddress = $hostConfig.PortBindings.'8000/tcp'[0].HostIp
    if ($hostAddress -ne '127.0.0.1') {
        throw "Product port was not bound exclusively to loopback: $hostAddress"
    }

    if ($capabilities.readOnlyRootFilesystem) {
        $readOnlyProbe = "from pathlib import Path; p=Path('/app/.wslc-read-only-probe'); p.write_text('x'); p.unlink()"
        $writeResult = Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-product-app", 'python', '-c', $readOnlyProbe) -AllowFailure
        if ($writeResult.ExitCode -eq 0 -or $writeResult.Text -notmatch 'Read-only file system') {
            throw 'The read-only root-filesystem request did not enforce EROFS on /app.'
        }
    } else {
        $writableProbe = "from pathlib import Path; p=Path('/app/.wslc-read-only-probe'); p.write_text('x'); p.unlink()"
        Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-product-app", 'python', '-c', $writableProbe) | Out-Null
        $evidence.runtime.readOnlyRootfsProbe = 'Writable: wslc run has no --read-only option.'
    }
    if ($capabilities.dropCapabilities) {
        $capsCheck = "from pathlib import Path; value=next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:')); assert int(value,16)==0, value"
        Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-product-app", 'python', '-c', $capsCheck) | Out-Null
    }

    $bootstrap = @(
        'committee', 'bootstrap', '--idempotency-key', "wslc-$runId", '--name', 'WSLc qualification committee',
        '--ihk', 'IHK WSLc Test', '--occupation', 'WSLc test occupation', '--chair-first-name', 'WSLc',
        '--chair-last-name', 'Qualification', '--chair-email', 'wslc-qualification@example.invalid',
        '--chair-member-status', 'ordinary', '--chair-representing-side', 'employee'
    )
    $bootstrapText = Invoke-Wslc -Arguments (@(
        'exec', '--user', '10001:10001', "$script:resourcePrefix-product-app", 'lzug-admin',
        '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json'
    ) + $bootstrap)
    $bootstrapResult = $bootstrapText.Text | ConvertFrom-Json
    if (-not $bootstrapResult.ok -or $bootstrapResult.result.committee_id -le 0) {
        throw "Could not write a synthetic record through the delivered CLI: $($bootstrapText.Text)"
    }
    $createdCommitteeId = $bootstrapResult.result.committee_id
    Invoke-Wslc -Arguments @('container', 'stop', "$script:resourcePrefix-product-app") | Out-Null
    Invoke-Wslc -Arguments @('container', 'start', "$script:resourcePrefix-product-app") | Out-Null
    Test-LzugApiReady -Url 'http://127.0.0.1:18080'
    $replayedText = Invoke-Wslc -Arguments (@(
        'exec', '--user', '10001:10001', "$script:resourcePrefix-product-app", 'lzug-admin',
        '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json'
    ) + $bootstrap)
    $replayed = $replayedText.Text | ConvertFrom-Json
    if (-not $replayed.ok -or -not $replayed.result.replayed -or
        $replayed.result.committee_id -ne $createdCommitteeId) {
        throw 'The CLI bootstrap record did not persist across stop/start.'
    }
    $evidence.runtime.product = [ordered]@{
        lifecycle = 'ready'
        healthRevision = $productHealth.revision
        adminSocket = 'listening, uid=10001, gid=10001, mode=0660'
        cliWriteReadAfterRestart = $true
        readOnlyRootfs = [bool]$capabilities.readOnlyRootFilesystem
        capabilitiesDropped = [bool]$capabilities.dropCapabilities
        noNewPrivileges = [bool]$capabilities.noNewPrivileges
    }

    $seedRun = @('run', '--rm', '--label', "$script:resourceLabel=$script:runId", '--tmpfs', '/tmp')
    if ($capabilities.readOnlyRootFilesystem) { $seedRun += '--read-only' }
    if ($capabilities.dropCapabilities) { $seedRun += @('--cap-drop', 'ALL') }
    if ($capabilities.noNewPrivileges) { $seedRun += @('--security-opt', 'no-new-privileges:true') }
    $seedRun += @('--mount', "type=volume,source=$demoVolume,target=/data", $seedImage)
    Invoke-Wslc -Arguments $seedRun | Out-Null
    Start-WslcApp -Name "$script:resourcePrefix-demo-app" -Image $demoImage -Volume $demoVolume -HostPort 18081 -ReadOnly:$capabilities.readOnlyRootFilesystem
    $demoStatus = Wait-ForHttp -Url 'http://127.0.0.1:18081/api/demo/status'
    if ($demoStatus.mode -ne 'demo' -or -not $demoStatus.initialized -or
        $demoStatus.initialization_status -ne 'ready' -or $demoStatus.seed_revision -ne $seedRevision) {
        throw "Demo image pair did not initialize from its built seed artifact: $($demoStatus | ConvertTo-Json -Compress)"
    }
    Invoke-Wslc -Arguments @('exec', "$script:resourcePrefix-demo-app", 'python', '-c', $uidCheck) | Out-Null
    $demoContainerInfo = Get-WslcContainerInfo -Container "$script:resourcePrefix-demo-app"
    if ($demoContainerInfo.Config.Labels[$script:resourceLabel] -ne $script:runId) {
        throw 'Resource label is missing from the demo container.'
    }
    Invoke-Wslc -Arguments @('container', 'stop', "$script:resourcePrefix-demo-app") | Out-Null
    Invoke-Wslc -Arguments @('container', 'start', "$script:resourcePrefix-demo-app") | Out-Null
    $demoAfterRestart = Wait-ForHttp -Url 'http://127.0.0.1:18081/api/demo/status'
    if ($demoAfterRestart.seed_revision -ne $seedRevision) {
        throw 'Demo app/seed identity did not persist across stop/start.'
    }
    $evidence.runtime.demo = [ordered]@{
        initialized = $demoStatus.initialized
        seedRevision = $demoStatus.seed_revision
        persistedAfterRestart = $true
    }

    $badBuildDirectory = Join-Path $env:RUNNER_TEMP "wslc-invalid-build-$script:runId"
    New-Item -ItemType Directory -Path $badBuildDirectory -Force | Out-Null
    @("FROM scratch", 'NOT_A_DOCKERFILE_DIRECTIVE invalid') |
        Set-Content -LiteralPath (Join-Path $badBuildDirectory 'Dockerfile')
    $invalidImage = "$script:resourcePrefix-invalid:local"
    $badBuild = Invoke-Wslc -Arguments @(
        'build', '--label', "$script:resourceLabel=$script:runId",
        '--file', (Join-Path $badBuildDirectory 'Dockerfile'),
        '--tag', $invalidImage, $badBuildDirectory
    ) -AllowFailure
    if ($badBuild.ExitCode -eq 0) {
        $ownedImages.Add($invalidImage)
        throw 'The intentionally invalid Dockerfile unexpectedly built successfully.'
    }
    $evidence.runtime.failedBuild = [ordered]@{
        exitCode = $badBuild.ExitCode
        diagnostic = ($badBuild.Text -split "`n" | Select-Object -Last 8) -join "`n"
        fallbackEngine = 'none; the qualification invokes wslc.exe directly'
    }
} catch {
    $failure = $_
    $evidence.failure = $_.Exception.Message
} finally {
    foreach ($container in $ownedContainers) {
        $cleanup = Invoke-Wslc -Arguments @('container', 'remove', '--force', $container) -AllowFailure
        if ($cleanup.ExitCode -ne 0) { $cleanupFailures.Add("container ${container}: $($cleanup.Text)") }
        else { $evidence.cleanup.containers += $container }
    }
    foreach ($volume in $ownedVolumes) {
        $cleanup = Invoke-Wslc -Arguments @('volume', 'remove', '--force', $volume) -AllowFailure
        if ($cleanup.ExitCode -ne 0) { $cleanupFailures.Add("volume ${volume}: $($cleanup.Text)") }
        else { $evidence.cleanup.volumes += $volume }
    }
    foreach ($image in $ownedImages) {
        $cleanup = Invoke-Wslc -Arguments @('image', 'remove', '--force', $image) -AllowFailure
        if ($cleanup.ExitCode -ne 0) { $cleanupFailures.Add("image ${image}: $($cleanup.Text)") }
        else { $evidence.cleanup.images += $image }
    }
    if ($cleanupFailures.Count -gt 0) {
        foreach ($cleanupFailure in $cleanupFailures) { $evidence.blockers.Add("Resource cleanup failed: $cleanupFailure") }
    }
    if ($null -ne $badBuildDirectory -and (Test-Path -LiteralPath $badBuildDirectory)) {
        Remove-Item -LiteralPath $badBuildDirectory -Recurse -Force
    }
    $evidencePath = Join-Path $outputDirectory 'qualification-evidence.json'
    $evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $evidencePath -Encoding utf8
    Pop-Location
}

if ($null -ne $failure) { throw $failure }
if ($evidence.blockers.Count -gt 0) {
    throw "wslc qualification is incomplete: $($evidence.blockers -join ' ')"
}
Write-Host "wslc qualification passed. Evidence: $evidencePath"
