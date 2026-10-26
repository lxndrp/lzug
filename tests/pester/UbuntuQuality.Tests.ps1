BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '../../development/ubuntu-quality/runner-contract.psm1') -Force
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
