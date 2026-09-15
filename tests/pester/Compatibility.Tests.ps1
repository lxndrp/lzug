BeforeAll {
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
}

Describe 'supported compatibility boundary' {
    It 'keeps the legacy migration fixture and current image contract explicit' {
        $documentation = Join-Path $PSScriptRoot '../../docs/developers/development.md'
        (Get-Content -Raw $documentation) | Should -Match 'OCI- oder Compose-Regel'
        (Get-Content -Raw (Join-Path $PSScriptRoot '../../compose.yaml')) | Should -Match 'restart:'
        (Get-LzugImage) | Should -Not -BeNullOrEmpty
    }
}
