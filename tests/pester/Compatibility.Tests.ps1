BeforeAll {
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
}

Describe 'v0.6.0 restore and explicit forward migration' {
    BeforeAll {
        # A release-form local fixture is necessary: dev builds correctly refuse upgrades.
        # This does not create a Git tag or publish a release.
        $fixture = New-LzugFixture "$TestDrive/legacy" -Image 'lzug-app:0.0.0-rc.0-contract'
        $legacy = 'ghcr.io/lxndrp/lzug@sha256:00e467d8acd6602ba8b4259b3f2a4e51ec98273e0be551f367e5979d5c780fe6'
        $legacyContainer = "$($fixture.Name)-legacy"
        Initialize-LzugFixture $fixture -Legacy
        Invoke-LzugNative docker @('pull', '--platform', 'linux/amd64', $legacy) | Out-Null
        # Keep the legacy identity in the CLI-only volume; return only the public key.
        $public = (Invoke-LzugNative docker @('run', '--rm', '--platform', 'linux/amd64', '--user', '10002:10001', '--mount', "type=volume,source=$($fixture.Work),target=/work,volume-nocopy", '--entrypoint', 'python', $legacy, '-c', @'
import os
from pathlib import Path
from backend.backup_restore import generate_recipient_keypair
public, private = generate_recipient_keypair()
os.umask(0o077)
Path('/work/legacy.key').write_text(private)
print(public)
'@)).Trim()
        Add-Content "$($fixture.Directory)/compose.env" "LZUG_BACKUP_RECIPIENT_PUBLIC_KEY=$public"
        Invoke-LzugNative docker @('run', '--detach', '--platform', 'linux/amd64', '--name', $legacyContainer, '--read-only', '--tmpfs', '/tmp', '--env', "LZUG_BACKUP_RECIPIENT_PUBLIC_KEY=$public", '--mount', "type=volume,source=$($fixture.Data),target=/data", $legacy, '--host', '0.0.0.0', '--port', '8000', '--init') | Out-Null
        $deadline = [DateTime]::UtcNow.AddSeconds(90)
        do {
            & docker exec $legacyContainer python -m backend.healthcheck *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($LASTEXITCODE -ne 0) { throw 'Pinned v0.6.0 fixture did not become live.' }
        $seed = @{version=1; command='committee-bootstrap'; arguments=@{
            idempotency_key='legacy-persistence'
            committee=@{name='Legacy committee'; ihk='IHK Test'; occupation='Test'}
            chair=@{mode='new'; first_name='Legacy'; last_name='Chair'; email='legacy-chair@example.invalid'; member_status='ordinary'; representing_side='employee'}
        }}
        $seeded = Invoke-LzugNative docker @('exec', '-i', $legacyContainer, 'python', '-m', 'backend.admin', '--protocol', '1') -InputText ($seed | ConvertTo-Json -Depth 5 -Compress) | ConvertFrom-Json
        $seeded.ok | Should -BeTrue
        # The supported old CLI protocol creates and restores the old artifact.
        $request = '{"version":1,"command":"backup-create","arguments":{}}'
        $created = Invoke-LzugNative docker @('exec', '-i', $legacyContainer, 'python', '-m', 'backend.admin', '--protocol', '1') -InputText $request | ConvertFrom-Json
        $created.ok | Should -BeTrue
        $artifact = $created.result.artifact
        $private = (Invoke-LzugNative docker @('run', '--rm', '--network', 'none', '--user', '10002:10001', '--mount', "type=volume,source=$($fixture.Work),target=/work,volume-nocopy,readonly", '--entrypoint', 'cat', $fixture.Image, '/work/legacy.key')).Trim()
        foreach ($command in @('artifact-verify', 'backup-restore')) {
            $request = @{version=1; command=$command; arguments=@{artifact=$artifact; recipient_private_key=$private}}
            if ($command -eq 'backup-restore') { $request.arguments.replace = $true }
            $result = Invoke-LzugNative docker @('exec', '-i', $legacyContainer, 'python', '-m', 'backend.admin', '--protocol', '1') -InputText ($request | ConvertTo-Json -Compress) | ConvertFrom-Json
            $result.ok | Should -BeTrue
            $result.result.source_application_version | Should -Be '0.6.0'
        }
        $private = $null
        Invoke-LzugNative docker @('cp', "${legacyContainer}:/data/backups/$artifact", "$($fixture.Directory)/legacy.lzug") | Out-Null
        # docker cp assigns the host owner. Only this encrypted artifact may be
        # read by the non-root image UID across a Linux bind mount, never its key.
        [System.IO.File]::SetUnixFileMode("$($fixture.Directory)/legacy.lzug", [System.IO.UnixFileMode]420)
        Invoke-LzugNative docker @('rm', '--force', $legacyContainer) | Out-Null
        # Convert only the test identity encoding; the migration itself uses the shipped CLI.
        Invoke-LzugNative docker @('run', '--rm', '--network', 'none', '--user', '10002:10001', '--mount', "type=volume,source=$($fixture.Work),target=/work,volume-nocopy", '--entrypoint', 'python', $fixture.Image, '-c', @'
import base64, os
from pathlib import Path
from backend.operations.backup_recipients import _bech32
encoded = Path('/work/legacy.key').read_text().split(':', 1)[1]
raw = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
os.umask(0o077)
Path('/work/key.age').write_text(_bech32('age-secret-key-', raw).upper() + '\n')
'@) | Out-Null
        Start-LzugFixture $fixture -State 'migration_required'
    }
    AfterAll {
        try {
            if ($legacyContainer) { & docker rm --force $legacyContainer *> $null }
        } finally { Remove-LzugFixture $fixture }
    }

    It 'preserves legacy storage and refuses unapproved migration while remaining live' {
        Assert-LzugRuntime $fixture
        (Invoke-WebRequest "$($fixture.Url)/api/ready" -SkipHttpErrorCheck).StatusCode | Should -Be 503
        (Invoke-WebRequest "$($fixture.Url)/api/candidates" -SkipHttpErrorCheck).StatusCode | Should -Be 503
        $plan = Invoke-LzugCli $fixture @('upgrade', 'status')
        $plan.result.supported | Should -BeTrue
        $plan.result.migration.current | Should -Not -Be $plan.result.migration.target
        $rejected = Invoke-LzugCli $fixture @('upgrade', 'apply', '--backup-output', '/work/unapproved.lzug', '--identity-file', '/work/key.age', '--force') -ExpectedExit 2
        $rejected.error.class | Should -Be 'invalid_invocation'
        (Invoke-LzugCli $fixture @('upgrade', 'status')).result.plan_id | Should -Be $plan.result.plan_id
        # The legacy artifact must not be silently accepted as a current age artifact.
        $inspection = Invoke-LzugNative docker @('run', '--rm', '--network', 'none', '--read-only', '--mount', "type=bind,source=$($fixture.Directory)/legacy.lzug,target=/legacy.lzug,readonly", '--entrypoint', 'lzug-admin', $fixture.Image, '--json', 'artifact', 'inspect', '--artifact', '/legacy.lzug') -ExpectedExit 40 | ConvertFrom-Json
        $inspection.error.class | Should -Be 'artifact_legacy_v1'
    }

    It 'applies the migration via the delivered CLI and remains ready after restart' {
        $applied = Invoke-LzugCli $fixture @('upgrade', 'apply', '--backup-output', '/work/pre-upgrade.lzug', '--identity-file', '/work/key.age', '--confirm-irreversible', '--force')
        $applied.result.job_id | Should -Not -BeNullOrEmpty
        Wait-LzugReady $fixture.Url
        Invoke-LzugCompose $fixture @('restart', 'lzug') | Out-Null
        Update-LzugUrl $fixture
        Wait-LzugReady $fixture.Url
        Assert-LzugRuntime $fixture
        $status = Invoke-LzugCli $fixture @('upgrade', 'status')
        $status.result.migration.current | Should -Be $status.result.migration.target
        $bootstrap = @('committee', 'bootstrap', '--idempotency-key', 'legacy-persistence', '--name', 'Legacy committee', '--ihk', 'IHK Test', '--occupation', 'Test', '--chair-first-name', 'Legacy', '--chair-last-name', 'Chair', '--chair-email', 'legacy-chair@example.invalid', '--chair-member-status', 'ordinary', '--chair-representing-side', 'employee')
        $preserved = Assert-LzugPersistedCommittee $fixture $bootstrap
        $preserved.committee_id | Should -Be $seeded.result.committee_id
        (Invoke-LzugCli $fixture @('backup', 'create', '--output', '/work/current.lzug')).result.artifact_type | Should -Be 'backup'
        (Invoke-LzugCli $fixture @('backup', 'verify', '--artifact', '/work/current.lzug', '--identity-file', '/work/key.age')).result.artifact_type | Should -Be 'backup'
    }
}
