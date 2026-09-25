BeforeAll {
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
}

Describe 'product image through the supported Compose runtime' {
    BeforeAll {
        $fixture = New-LzugFixture "$TestDrive/runtime"
        Initialize-LzugFixture $fixture
        Start-LzugFixture $fixture
    }
    AfterAll { Remove-LzugFixture $fixture }

    It 'serves the packaged frontend, health identity and protected HTTP boundary' {
        Assert-LzugRuntime $fixture
        $backend = Invoke-LzugNative docker @('exec', $fixture.Container, 'cat', '/app/backend/src/build-metadata.json') | ConvertFrom-Json
        $frontend = Invoke-LzugNative docker @('exec', $fixture.Container, 'cat', '/app/frontend/build-metadata.json') | ConvertFrom-Json
        $cli = Invoke-LzugNative docker @('exec', $fixture.Container, 'lzug-admin', '--build-metadata') | ConvertFrom-Json
        $revision = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{ index .Config.Labels "org.opencontainers.image.revision" }}', $fixture.Image)).Trim()
        $revision | Should -Match '^[0-9a-f]{40}$'
        $version = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{ index .Config.Labels "org.opencontainers.image.version" }}', $fixture.Image)).Trim()
        foreach ($metadata in @($backend, $frontend, $cli)) {
            $metadata.revision | Should -Be $revision
            $metadata.identity | Should -Be $backend.identity
        }
        $backend.identity | Should -Be $version
        $runtime = Invoke-LzugNative docker @('inspect', $fixture.Container) | ConvertFrom-Json
        $runtime[0].HostConfig.Privileged | Should -BeFalse
        $runtime[0].HostConfig.CapDrop | Should -Contain 'ALL'
        $runtime[0].HostConfig.SecurityOpt | Should -Contain 'no-new-privileges:true'
        $runtime[0].HostConfig.PortBindings.'8000/tcp'[0].HostIp | Should -Be '127.0.0.1'
        $health = Invoke-WebRequest "$($fixture.Url)/api/health"
        ($health.Content | ConvertFrom-Json).revision | Should -Be $revision
        ($health.Content | ConvertFrom-Json).version | Should -Be $version
        $health.Headers['X-Content-Type-Options'] | Should -Contain 'nosniff'
        $health.Headers['X-Frame-Options'] | Should -Contain 'DENY'
        ($health.Headers['Content-Security-Policy'] -join ';') | Should -Match 'frame-ancestors.*none'
        ($health.Headers['Strict-Transport-Security'] -join ';') | Should -Match 'max-age=31536000'
        (Invoke-WebRequest "$($fixture.Url)/dashboard").Content | Should -Match '<app-root'
        foreach ($case in @(@('/assets/missing.svg', 404), @('/api', 401), @('/api/candidates', 401))) {
            (Invoke-WebRequest "$($fixture.Url)$($case[0])" -SkipHttpErrorCheck).StatusCode | Should -Be $case[1]
        }
        (Invoke-WebRequest "$($fixture.Url)/api/health" -Headers @{Origin='https://blocked.example.invalid'} -SkipHttpErrorCheck).StatusCode | Should -Be 403
        $status = Invoke-LzugNative docker @('exec', '--user', '10001:10001', $fixture.Container, 'lzug-admin', '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json', 'system', 'status') | ConvertFrom-Json
        $status.ok | Should -BeTrue
        $status.result.runtime.ready | Should -BeTrue
    }

    It 'persists a supported CLI write over restart and stop/start with unchanged socket protection' {
        $bootstrap = @('committee', 'bootstrap', '--idempotency-key', 'runtime-persistence', '--name', 'Runtime committee', '--ihk', 'IHK Test', '--occupation', 'Test occupation', '--chair-first-name', 'Test', '--chair-last-name', 'Chair', '--chair-email', 'runtime-chair@example.invalid', '--chair-member-status', 'ordinary', '--chair-representing-side', 'employee')
        $created = Invoke-LzugCli $fixture $bootstrap
        $created.result.committee_id | Should -BeGreaterThan 0
        foreach ($transition in @('restart', 'stop/start')) {
            if ($transition -eq 'restart') { Invoke-LzugCompose $fixture @('restart', 'lzug') | Out-Null }
            else {
                Invoke-LzugCompose $fixture @('stop', 'lzug') | Out-Null
                (Invoke-LzugNative docker @('inspect', '--format', '{{.State.Status}}', $fixture.Container)).Trim() | Should -Be 'exited'
                Invoke-LzugCompose $fixture @('start', 'lzug') | Out-Null
            }
            Update-LzugUrl $fixture
            Wait-LzugReady $fixture.Url
            Assert-LzugRuntime $fixture
            $replayed = Assert-LzugPersistedCommittee $fixture $bootstrap
            $replayed.committee_id | Should -Be $created.result.committee_id
            $replayed.person_ids | Should -Be $created.result.person_ids
        }
        # Recreate the container to distinguish persisted data from its writable layer.
        Invoke-LzugCompose $fixture @('up', '-d', '--force-recreate') | Out-Null
        $fixture.Container = (Invoke-LzugCompose $fixture @('ps', '-q', 'lzug')).Trim()
        Update-LzugUrl $fixture
        Wait-LzugReady $fixture.Url
        Assert-LzugPersistedCommittee $fixture $bootstrap | Out-Null
        Assert-LzugRuntime $fixture
        # A substituted empty volume must fail the very same persistence assertion.
        $lost = New-LzugFixture "$TestDrive/lost-data"
        try {
            Initialize-LzugFixture $lost
            Start-LzugFixture $lost
            { Assert-LzugPersistedCommittee $lost $bootstrap } | Should -Throw '*previously committed bootstrap*'
        } finally { Remove-LzugFixture $lost }
    }

    It 'opens and exits the delivered interactive CLI on a real terminal' {
        Invoke-LzugNative docker @('exec', '--user', '10001:10001', $fixture.Container, 'python', '-c', @'
import os, pty, select, subprocess, time
master, slave = pty.openpty()
process = subprocess.Popen(
    ['lzug-admin', '--endpoint', 'unix:///run/lzug-admin/admin.sock', 'cli'],
    stdin=slave, stdout=slave, stderr=slave,
)
os.close(slave)
try:
    commands = iter((b'system\r', b'status\r', b'beenden\r'))
    pending = b''
    output = b''
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if select.select([master], [], [], 0.2)[0]:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            pending += chunk
            if pending.endswith((b'> ', b'Beenden): ')):
                command = next(commands, None)
                if command is not None:
                    os.write(master, command)
                pending = b''
        if process.poll() is not None:
            break
    assert process.wait(timeout=2) == 0
    assert b'system status erfolgreich (Exit Code 0)' in output
    assert 'Sitzung beendet.'.encode() in output
finally:
    if process.poll() is None:
        process.kill()
    process.wait()
    os.close(master)
'@) | Out-Null
    }

    It 'enforces HTTP actor, committee, cookie and secret-free logging boundaries' {
        $committees = @('actor', 'foreign') | ForEach-Object {
            Invoke-LzugCli $fixture @('committee', 'bootstrap', '--idempotency-key', "http-$_", '--name', "HTTP $_", '--ihk', 'IHK Test', '--occupation', 'Test', '--chair-first-name', 'Test', '--chair-last-name', $_, '--chair-email', "http-$_@example.invalid", '--chair-member-status', 'ordinary', '--chair-representing-side', 'employee')
        }
        # Authentication setup is fixture-only; all domain writes below use HTTP.
        $sessions = Invoke-LzugNative docker @('exec', $fixture.Container, 'python', '-c', @'
import json, sys
from backend.identity.auth import AuthenticationRepository
repository = AuthenticationRepository()
operator = repository.create_account('http-operator@example.invalid', is_operator=True)
result = []
for account in (int(sys.argv[1]), int(sys.argv[2]), operator['id']):
    credentials = repository.create_session(account)
    result.append({'token': credentials.token, 'csrf': credentials.csrf_token})
print(json.dumps(result))
'@, "$($committees[0].result.account_ids[0])", "$($committees[1].result.account_ids[0])") | ConvertFrom-Json
        $headers = @($sessions | ForEach-Object { @{Cookie="__Host-lzug_session=$($_.token)"; 'X-CSRF-Token'=$_.csrf} })
        (Invoke-WebRequest "$($fixture.Url)/api/candidates" -Headers $headers[2] -SkipHttpErrorCheck).StatusCode | Should -Be 403
        $rounds = @(for ($i=0; $i -lt 2; $i++) {
            $body = @{season='summer'; year=2030; committee_id=$committees[$i].result.committee_id; name="HTTP round $i"; created_by_member_id=999999} | ConvertTo-Json
            $round = Invoke-RestMethod "$($fixture.Url)/api/exam-rounds" -Method Post -Headers $headers[$i] -ContentType 'application/json' -Body $body
            $round.created_by_member_id | Should -Be $committees[$i].result.membership_ids[0]
            $round
        })
        (Invoke-WebRequest "$($fixture.Url)/api/exam-rounds/$($rounds[1].id)" -Headers $headers[0] -SkipHttpErrorCheck).StatusCode | Should -Be 404
        $foreign = @{season='summer'; year=2030; committee_id=$committees[1].result.committee_id; name='Forbidden'; created_by_member_id=$committees[0].result.membership_ids[0]} | ConvertTo-Json
        (Invoke-WebRequest "$($fixture.Url)/api/exam-rounds" -Method Post -Headers $headers[0] -ContentType 'application/json' -Body $foreign -SkipHttpErrorCheck).StatusCode | Should -Be 403
        $rotated = Invoke-WebRequest "$($fixture.Url)/api/session/rotate" -Method Post -Headers $headers[0]
        ($rotated.Headers['Set-Cookie'] -join ';') | Should -Match '__Host-lzug_session=.*Secure.*HttpOnly'
        ($rotated.Headers['Set-Cookie'] -join ';') | Should -Match 'SameSite=Strict'
        $marker = 'pester-secret-' + [guid]::NewGuid().ToString('N')
        $login = @{email="$marker@example.invalid"; password=$marker; second_factor='000000'} | ConvertTo-Json
        (Invoke-WebRequest "$($fixture.Url)/api/auth/login" -Method Post -ContentType 'application/json' -Body $login -SkipHttpErrorCheck).StatusCode | Should -Be 401
        $logs = (& docker logs $fixture.Container 2>&1) -join "`n"
        $LASTEXITCODE | Should -Be 0
        $logs.Contains($marker) | Should -BeFalse
    }

    It 'runs delivered CLI diagnostics, account workflows and protected artifact roundtrips' {
        $invitation = Invoke-LzugCli $fixture @('account', 'invite', '--email', 'operator-contract@example.invalid')
        $consumed = Invoke-LzugCli $fixture @('account', 'consume-invitation') -InputText $invitation.result.token
        $consumed.result.account.email | Should -Be 'operator-contract@example.invalid'
        foreach ($command in @('status', 'config', 'doctor')) {
            $diagnostic = Invoke-LzugCli $fixture @('system', $command)
            $diagnostic.result.runtime.ready | Should -BeTrue
            $diagnostic.result.socket.state | Should -Be 'listening'
            ($diagnostic | ConvertTo-Json -Depth 30) | Should -Not -Match ([regex]::Escape($invitation.result.token))
        }
        Invoke-LzugCli $fixture @('recipient-key', 'generate', '--identity-file', '/work/key.age', '--recipient-file', '/work/key.pub') | Out-Null
        Invoke-LzugCli $fixture @('recipient-key', 'generate', '--identity-file', '/work/wrong.age', '--recipient-file', '/work/wrong.pub') | Out-Null
        Invoke-LzugCli $fixture @('backup', 'recipient', 'set', '--identity-file', '/work/key.age') | Out-Null
        $backup = Invoke-LzugCli $fixture @('backup', 'create', '--output', '/work/backup.lzug')
        $backup.result.artifact_type | Should -Be 'backup'
        (Invoke-LzugCli $fixture @('backup', 'verify', '--artifact', '/work/backup.lzug', '--identity-file', '/work/key.age')).result.artifact_type | Should -Be 'backup'
        $wrong = Invoke-LzugCli $fixture @('backup', 'verify', '--artifact', '/work/backup.lzug', '--identity-file', '/work/wrong.age') -ExpectedExit 2
        $wrong.error.class | Should -Be 'recipient_key_mismatch'
        $recipient = (Invoke-LzugCli $fixture @('backup', 'recipient', 'show')).result.recipient
        (Invoke-LzugCli $fixture @('export', 'create', '--recipient', $recipient, '--output', '/work/export.lzug', '--force')).result.artifact_type | Should -Be 'full_export'
        (Invoke-LzugCli $fixture @('export', 'verify', '--artifact', '/work/export.lzug', '--identity-file', '/work/key.age')).result.artifact_type | Should -Be 'full_export'
        $refused = Invoke-LzugCli $fixture @('backup', 'restore', '--artifact', '/work/backup.lzug', '--identity-file', '/work/key.age', '--force') -ExpectedExit 29
        $refused.error.class | Should -Be 'replace_confirmation_required'
        $restored = Invoke-LzugCli $fixture @('backup', 'restore', '--artifact', '/work/backup.lzug', '--identity-file', '/work/key.age', '--replace', '--force')
        $restored.result.phases | Should -Be @('precheck', 'prepared_restore', 'migration', 'postcheck', 'activation')
        Wait-LzugReady $fixture.Url
        (Invoke-LzugCli $fixture @('upgrade', 'rollback') -ExpectedExit 28).error.class | Should -Be 'rollback_not_supported'
        $private = (Invoke-LzugNative docker @('run', '--rm', '--network', 'none', '--user', '10002:10001', '--mount', "type=volume,source=$($fixture.Work),target=/work,volume-nocopy,readonly", '--entrypoint', 'cat', $fixture.Image, '/work/key.age')).Trim()
        $encoded = @($backup, $wrong, $refused, $restored) | ConvertTo-Json -Depth 30
        $encoded.Contains($private) | Should -BeFalse
        $logs = (& docker logs $fixture.Container 2>&1) -join "`n"
        $LASTEXITCODE | Should -Be 0
        $logs.Contains($private) | Should -BeFalse
        Invoke-LzugNative docker @('exec', $fixture.Container, 'test', '!', '-e', '/work/key.age') | Out-Null
    }

    It 'rejects an unsafe socket directory instead of weakening the runtime guard' {
        Invoke-LzugCompose $fixture @('stop', 'lzug') | Out-Null
        $prepare = @('run', '--rm', '--no-deps', '--user', '0:0', '--cap-add', 'FOWNER', '--entrypoint', 'chmod', 'lzug')
        try {
            Invoke-LzugCompose $fixture ($prepare + @('0777', '/run/lzug-admin')) | Out-Null
            Invoke-LzugNative docker @('run', '--rm', '--read-only', '--tmpfs', '/tmp', '--mount', "type=volume,source=$($fixture.Socket),target=/run/lzug-admin,volume-nocopy", '--entrypoint', 'timeout', $fixture.Image, '5s', 'python', '-m', 'backend.server', '--admin-socket-dir', '/run/lzug-admin', '--admin-socket-gid', '10001') -ExpectedExit 1 | Out-Null
        } finally {
            Invoke-LzugCompose $fixture ($prepare + @('0750', '/run/lzug-admin')) | Out-Null
            Invoke-LzugCompose $fixture @('start', 'lzug') | Out-Null
            Update-LzugUrl $fixture
            Wait-LzugReady $fixture.Url
        }
        Assert-LzugRuntime $fixture
    }
}
