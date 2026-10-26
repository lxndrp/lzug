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
}
