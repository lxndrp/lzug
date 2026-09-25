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

    It 'starts the built image with its packaged frontend, shared identity and CLI socket' {
        $backend = Invoke-LzugNative docker @('exec', $fixture.Container, 'cat', '/app/backend/src/build-metadata.json') | ConvertFrom-Json
        $frontend = Invoke-LzugNative docker @('exec', $fixture.Container, 'cat', '/app/frontend/build-metadata.json') | ConvertFrom-Json
        $cli = Invoke-LzugNative docker @('exec', $fixture.Container, 'lzug-admin', '--build-metadata') | ConvertFrom-Json
        $revision = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{ index .Config.Labels "org.opencontainers.image.revision" }}', $fixture.Image)).Trim()
        $version = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{ index .Config.Labels "org.opencontainers.image.version" }}', $fixture.Image)).Trim()
        $revision | Should -Match '^[0-9a-f]{40}$'
        foreach ($metadata in @($backend, $frontend, $cli)) {
            $metadata.revision | Should -Be $revision
            $metadata.identity | Should -Be $backend.identity
        }
        $backend.identity | Should -Be $version

        $runtime = Invoke-LzugNative docker @('inspect', $fixture.Container) | ConvertFrom-Json
        $runtime[0].Config.User | Should -Be '10001:10001'
        $runtime[0].HostConfig.ReadonlyRootfs | Should -BeTrue
        $runtime[0].HostConfig.Privileged | Should -BeFalse
        $runtime[0].HostConfig.CapDrop | Should -Contain 'ALL'
        $runtime[0].HostConfig.SecurityOpt | Should -Contain 'no-new-privileges:true'
        $runtime[0].HostConfig.PortBindings.'8000/tcp'[0].HostIp | Should -Be '127.0.0.1'

        Assert-LzugRuntime $fixture
        $health = Invoke-WebRequest "$($fixture.Url)/api/health"
        ($health.Content | ConvertFrom-Json).revision | Should -Be $revision
        ($health.Content | ConvertFrom-Json).version | Should -Be $version
        (Invoke-WebRequest "$($fixture.Url)/dashboard").Content | Should -Match '<app-root'

        $status = Invoke-LzugNative docker @('exec', '--user', '10001:10001', $fixture.Container, 'lzug-admin', '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json', 'system', 'status') | ConvertFrom-Json
        $status.ok | Should -BeTrue
        $status.result.runtime.ready | Should -BeTrue
        $status.result.socket.state | Should -Be 'listening'
    }

    It 'preserves one supported data roundtrip when Compose recreates the container' {
        $bootstrap = @('committee', 'bootstrap', '--idempotency-key', 'runtime-persistence', '--name', 'Runtime committee', '--ihk', 'IHK Test', '--occupation', 'Test occupation', '--chair-first-name', 'Test', '--chair-last-name', 'Chair', '--chair-email', 'runtime-chair@example.invalid', '--chair-member-status', 'ordinary', '--chair-representing-side', 'employee')
        $created = Invoke-LzugCli $fixture $bootstrap
        $created.result.committee_id | Should -BeGreaterThan 0

        Invoke-LzugCompose $fixture @('up', '-d', '--force-recreate') | Out-Null
        $fixture.Container = (Invoke-LzugCompose $fixture @('ps', '-q', 'lzug')).Trim()
        Update-LzugUrl $fixture
        Wait-LzugReady $fixture.Url
        $replayed = Assert-LzugPersistedCommittee $fixture $bootstrap
        $replayed.committee_id | Should -Be $created.result.committee_id
        $replayed.person_ids | Should -Be $created.result.person_ids
    }
}
