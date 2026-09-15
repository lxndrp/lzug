BeforeAll {
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
    $image = Get-LzugImage
}

Describe 'packaged container contract' {
    It 'uses the non-root runtime and immutable build identity' {
        Assert-LzugDocker -Image $image
        $user = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{.Config.User}}', $image)).Trim()
        $user | Should -Be '10001:10001'
        $revision = (Invoke-LzugNative docker @('image', 'inspect', '--format', '{{ index .Config.Labels "org.opencontainers.image.revision" }}', $image)).Trim()
        $revision | Should -Match '^[0-9a-f]{40}$'
    }

    It 'has the expected healthcheck and read-only runtime boundary' {
        Assert-LzugDocker -Image $image
        $config = Invoke-LzugNative docker @('image', 'inspect', '--format', '{{json .Config}}', $image) | ConvertFrom-Json
        $config.Healthcheck.Test -join ' ' | Should -Be 'CMD python -m backend.healthcheck'
        $config.User | Should -Be '10001:10001'
    }
}

Describe 'compose contract' {
    It 'accepts the supported Compose model' {
        Assert-LzugDocker
        $env:LZUG_IMAGE = $image
        $json = Invoke-LzugNative docker @('compose', '-f', 'compose.yaml', 'config', '--format', 'json') | ConvertFrom-Json
        $service = $json.services.lzug
        $service.user | Should -Be '10001:10001'
        $service.read_only | Should -BeTrue
        $service.cap_drop | Should -Contain 'ALL'
        $service.volumes.target | Should -Contain '/data'
        $service.ports.host_ip | Should -Be '127.0.0.1'
        $service.healthcheck.test -join ' ' | Should -Be 'CMD python -m backend.healthcheck'
    }
}
