BeforeAll {
    . (Join-Path $PSScriptRoot '../../docs/publication/publication-artifact.ps1')
    $script:now = [datetimeoffset]'2026-09-26T12:00:00Z'
    $script:revision = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
}

Describe 'Publication artifact selection' {
    It 'selects the newest nonexpired artifact from a successful exact master revision' {
        $runs = @{ workflow_runs = @(
            @{ id = 100; head_sha = $script:revision; head_branch = 'master'; status = 'completed'; conclusion = 'success'; event = 'push' },
            @{ id = 101; head_sha = $script:revision; head_branch = 'master'; status = 'completed'; conclusion = 'success'; event = 'schedule' }
        ) }
        $artifacts = @{ artifacts = @(
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T11:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 101 } }
        ) }

        Get-ReusablePublicationRun -RunsPayload $runs -ArtifactsPayload $artifacts -Revision $script:revision -Now $script:now | Should -Be '101'
    }

    It 'rejects artifacts from other revisions, branches, events, failed runs, or expired entries' {
        $runs = @{ workflow_runs = @(
            @{ id = 100; head_sha = ('b' * 40); head_branch = 'master'; status = 'completed'; conclusion = 'success'; event = 'push' },
            @{ id = 101; head_sha = $script:revision; head_branch = 'feature'; status = 'completed'; conclusion = 'success'; event = 'push' },
            @{ id = 102; head_sha = $script:revision; head_branch = 'master'; status = 'completed'; conclusion = 'success'; event = 'pull_request' },
            @{ id = 103; head_sha = $script:revision; head_branch = 'master'; status = 'completed'; conclusion = 'failure'; event = 'push' }
        ) }
        $artifacts = @{ artifacts = @(
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 101 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 102 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 103 } }
        ) }

        Get-ReusablePublicationRun -RunsPayload $runs -ArtifactsPayload $artifacts -Revision $script:revision -Now $script:now | Should -BeNullOrEmpty
    }

    It 'rejects unrelated, empty, expired, and future-dated artifacts' {
        $runs = @{ workflow_runs = @(
            @{ id = 100; head_sha = $script:revision; head_branch = 'master'; status = 'completed'; conclusion = 'success'; event = 'push' }
        ) }
        $artifacts = @{ artifacts = @(
            @{ name = 'other-artifact'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 0; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $true; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T10:00:00Z'; expires_at = '2026-09-26T11:59:59Z'; workflow_run = @{ id = 100 } },
            @{ name = 'lzug-public-site'; expired = $false; size_in_bytes = 123; created_at = '2026-09-26T12:00:01Z'; expires_at = '2026-10-03T10:00:00Z'; workflow_run = @{ id = 100 } }
        ) }

        Get-ReusablePublicationRun -RunsPayload $runs -ArtifactsPayload $artifacts -Revision $script:revision -Now $script:now | Should -BeNullOrEmpty
    }

    It 'targets generator and configuration inputs for reproducibility checks only' {
        Test-PublicationReproducibility -Paths @('docs/publication/hugo.toml') | Should -BeTrue
        Test-PublicationReproducibility -Paths @('frontend/package-lock.json') | Should -BeTrue
        Test-PublicationReproducibility -Paths @('uv.lock') | Should -BeTrue
        Test-PublicationReproducibility -Paths @('docs/portal/produkt.md') | Should -BeFalse
        Test-PublicationReproducibility -Paths @('frontend/src/app/login/login.ts') | Should -BeFalse
    }
}
