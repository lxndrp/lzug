BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '../../development/ubuntu-quality/runner-contract.psm1') -Force
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
}

Describe 'Ubuntu quality runner resource contracts' {
    It 'accepts well-formed worktree scopes and rejects empty hyphen segments' {
        Test-LzugWorktreeScope 'a8d8' | Should -BeTrue
        Test-LzugWorktreeScope 'issue-1005-quality' | Should -BeTrue
        Test-LzugWorktreeScope 'a--b' | Should -BeFalse
        Test-LzugWorktreeScope 'a-' | Should -BeFalse
        Test-LzugWorktreeScope '-a' | Should -BeFalse
    }

    It 'accepts only a Unix endpoint resolving to the mounted local socket' {
        $socket = Join-Path $TestDrive 'docker.sock'
        $remoteSocket = Join-Path $TestDrive 'remote.sock'
        New-Item -ItemType File -Path $socket | Out-Null
        New-Item -ItemType File -Path $remoteSocket | Out-Null

        Test-LzugLocalDockerEndpoint "unix://$socket" $socket | Should -BeTrue
        Test-LzugLocalDockerEndpoint "unix://$remoteSocket" $socket | Should -BeFalse
        Test-LzugLocalDockerEndpoint 'tcp://docker.example.invalid:2376' $socket | Should -BeFalse
        Test-LzugLocalDockerEndpoint 'ssh://docker.example.invalid' $socket | Should -BeFalse
    }

    It 'requires both the exact runner name and its resource label before cleanup' {
        $labels = @{ 'lzug-codex-a8d8' = '' }

        Test-LzugRunnerContainerOwnership `
            'lzug-codex-a8d8-ubuntu-quality-run-1234' `
            'lzug-codex-a8d8-ubuntu-quality-run' `
            'lzug-codex-a8d8' `
            $labels | Should -BeTrue
        Test-LzugRunnerContainerOwnership `
            'lzug-codex-a8d8-ubuntu-quality-run-1234-backup' `
            'lzug-codex-a8d8-ubuntu-quality-run' `
            'lzug-codex-a8d8' `
            $labels | Should -BeFalse
        Test-LzugRunnerContainerOwnership `
            'lzug-codex-a8d8-ubuntu-quality-run-1234' `
            'lzug-codex-a8d8-ubuntu-quality-run' `
            'lzug-codex-other' `
            $labels | Should -BeFalse
    }

    It 'scopes quality images to the runner resource prefix' {
        $images = Get-LzugQualityImageReferences -ResourcePrefix 'lzug-codex-a8d8-ubuntu-quality'

        $images.App | Should -Be 'lzug-codex-a8d8-ubuntu-quality-product:0.0.0-dev.local'
        $images.Contract | Should -Be 'lzug-codex-a8d8-ubuntu-quality-product:0.0.0-rc.0-contract'
        $images.DemoApp | Should -Be 'lzug-codex-a8d8-ubuntu-quality-demo-app:local'
        $images.DemoSeed | Should -Be 'lzug-codex-a8d8-ubuntu-quality-demo-seed:local'
    }

    It 'scopes Pester fixture names, containers, networks, and volumes to the worktree label' {
        $previousResourceLabel = $env:LZUG_QUALITY_RESOURCE_LABEL
        $previousRuntimeBindAddress = $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS
        $env:LZUG_QUALITY_RESOURCE_LABEL = 'lzug-codex-a8d8'
        $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS = '172.17.0.1'
        try {
            $fixture = New-LzugFixture (Join-Path $TestDrive 'fixture')
            $fixture.Name | Should -Match '^lzug-codex-a8d8-pester-[0-9a-f]{32}$'
            $fixture.ResourceLabel | Should -Be 'lzug-codex-a8d8'
            $composeOverride = Get-Content -Raw (Join-Path $TestDrive 'fixture/socket.yaml')
            $composeOverride | Should -Match "(?s)services:\s+lzug:\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)contract_socket:\s+name:\s+lzug-codex-a8d8-pester-[0-9a-f]{32}-socket\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)lzug_data:\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)networks:\s+default:\s+name:\s+lzug-codex-a8d8-pester-[0-9a-f]{32}-network\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeEnvironment = Get-Content -Raw (Join-Path $TestDrive 'fixture/compose.env')
            $composeEnvironment | Should -Match 'LZUG_BIND_ADDRESS=172\.17\.0\.1'

            $containerName = "$($fixture.Name)-legacy"
            $runArguments = Get-LzugDockerRunArguments -Fixture $fixture -Name $containerName -Arguments @('--detach', '--platform', 'linux/amd64', 'image:tag')
            ($runArguments -join '|') | Should -Be "run|--name|$containerName|--label|lzug-codex-a8d8=|--detach|--platform|linux/amd64|image:tag"
            $volumeArguments = Get-LzugDockerVolumeCreateArguments -Fixture $fixture -Name $fixture.Work
            ($volumeArguments -join '|') | Should -Be "volume|create|--label|lzug-codex-a8d8=|$($fixture.Work)"
        } finally {
            if ($null -eq $previousResourceLabel) {
                Remove-Item Env:LZUG_QUALITY_RESOURCE_LABEL -ErrorAction SilentlyContinue
            } else {
                $env:LZUG_QUALITY_RESOURCE_LABEL = $previousResourceLabel
            }
            if ($null -eq $previousRuntimeBindAddress) {
                Remove-Item Env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS -ErrorAction SilentlyContinue
            } else {
                $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS = $previousRuntimeBindAddress
            }
        }
    }

    It 'uses the configured published-runtime host and defaults to loopback' {
        $previousRuntimeHost = $env:LZUG_QUALITY_RUNTIME_HOST
        $previousRuntimeBindAddress = $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS
        try {
            $fixture = @{ Compose = @('compose'); Url = '' }
            $env:LZUG_QUALITY_RUNTIME_HOST = 'host.docker.internal'
            $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS = '127.0.0.1'
            Mock Invoke-LzugCompose { '127.0.0.1:55010' }

            Update-LzugUrl $fixture

            $fixture.Url | Should -Be 'http://host.docker.internal:55010'

            Remove-Item Env:LZUG_QUALITY_RUNTIME_HOST -ErrorAction SilentlyContinue
            Remove-Item Env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS -ErrorAction SilentlyContinue
            Update-LzugUrl $fixture
            $fixture.Url | Should -Be 'http://127.0.0.1:55010'

            $env:LZUG_QUALITY_RUNTIME_HOST = '172.17.0.1'
            Update-LzugUrl $fixture
            $fixture.Url | Should -Be 'http://172.17.0.1:55010'
        } finally {
            if ($null -eq $previousRuntimeHost) {
                Remove-Item Env:LZUG_QUALITY_RUNTIME_HOST -ErrorAction SilentlyContinue
            } else {
                $env:LZUG_QUALITY_RUNTIME_HOST = $previousRuntimeHost
            }
            if ($null -eq $previousRuntimeBindAddress) {
                Remove-Item Env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS -ErrorAction SilentlyContinue
            } else {
                $env:LZUG_QUALITY_RUNTIME_BIND_ADDRESS = $previousRuntimeBindAddress
            }
        }
    }

    It 'uses a short shared temporary path for nested Docker bind-mount tests' {
        if ($IsLinux -and -not [string]::IsNullOrWhiteSpace($env:LZUG_QUALITY_RUNTIME_HOST)) {
            $temporaryRoot = [IO.Path]::GetFullPath($env:LZUG_PESTER_TMPDIR).TrimEnd(
                [IO.Path]::DirectorySeparatorChar
            )
            $testTemporaryPath = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
                [IO.Path]::DirectorySeparatorChar
            )
            $testTemporaryPath | Should -Be $temporaryRoot
            $temporaryRoot.Length | Should -BeLessThan 64
            $testDriveRoot = [IO.Path]::GetFullPath($TestDrive)
            $testDriveRoot.StartsWith(
                $temporaryRoot + [IO.Path]::DirectorySeparatorChar,
                [StringComparison]::Ordinal
            ) | Should -BeTrue
        }
    }

    It 'matches only the exact generated Buildx builder name' {
        Test-LzugBuilderOwnership `
            'lzug-codex-a8d8-ubuntu-quality-buildx' `
            'lzug-codex-a8d8-ubuntu-quality-buildx' | Should -BeTrue
        Test-LzugBuilderOwnership `
            'lzug-codex-a8d8-ubuntu-quality-buildx-other' `
            'lzug-codex-a8d8-ubuntu-quality-buildx' | Should -BeFalse
        Test-LzugBuilderOwnership `
            'lzug-codex-other-ubuntu-quality-buildx' `
            'lzug-codex-a8d8-ubuntu-quality-buildx' | Should -BeFalse
    }

    It 'reports cleanup failure after an otherwise successful quality run' {
        {
            Complete-LzugRunnerOutcome -TaskError $null -CleanupErrors @('Buildx builder cleanup failed')
        } | Should -Throw '*Ubuntu quality cleanup failed*'
    }

    It 'preserves the task failure when cleanup also fails' {
        try {
            throw 'quality task failed'
        } catch {
            $taskError = $_
        }

        $failureMessage = $null
        try {
            Complete-LzugRunnerOutcome -TaskError $taskError -CleanupErrors @('volume cleanup failed')
        } catch {
            $failureMessage = $_.Exception.Message
        }

        $failureMessage | Should -Be 'quality task failed'
    }
}
