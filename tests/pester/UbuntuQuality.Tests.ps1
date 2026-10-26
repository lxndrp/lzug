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
        $env:LZUG_QUALITY_RESOURCE_LABEL = 'lzug-codex-a8d8'
        try {
            $fixture = New-LzugFixture (Join-Path $TestDrive 'fixture')
            $fixture.Name | Should -Match '^lzug-codex-a8d8-pester-[0-9a-f]{32}$'
            $fixture.ResourceLabel | Should -Be 'lzug-codex-a8d8'
            $composeOverride = Get-Content -Raw (Join-Path $TestDrive 'fixture/socket.yaml')
            $composeOverride | Should -Match "(?s)services:\s+lzug:\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)contract_socket:\s+name:\s+lzug-codex-a8d8-pester-[0-9a-f]{32}-socket\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)lzug_data:\s+labels:\s+'lzug-codex-a8d8': ''"
            $composeOverride | Should -Match "(?s)networks:\s+default:\s+name:\s+lzug-codex-a8d8-pester-[0-9a-f]{32}-network\s+labels:\s+'lzug-codex-a8d8': ''"

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
