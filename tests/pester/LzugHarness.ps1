Set-StrictMode -Version Latest

function Invoke-LzugNative {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [int]$ExpectedExit = 0,
        [string]$InputText
    )
    $output = if ($PSBoundParameters.ContainsKey('InputText')) {
        $InputText | & $Command @Arguments 2>$null
    } else { & $Command @Arguments 2>$null }
    if ($LASTEXITCODE -ne $ExpectedExit) {
        # Native output can contain one-time credentials. Report only the boundary.
        $actualExit = $LASTEXITCODE
        $failureClass = 'unavailable'
        try {
            $candidate = ($output -join "`n" | ConvertFrom-Json).error.class
            if ($candidate -match '^[a-z_]+$') { $failureClass = $candidate }
        } catch { }
        throw "$Command exit mismatch: expected=$ExpectedExit actual=$actualExit class=$failureClass"
    }
    ($output | ForEach-Object { "$_" }) -join "`n"
}

function Assert-LzugDocker {
    param([string]$Image)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is unavailable.' }
    Invoke-LzugNative docker @('info', '--format', '{{.ServerVersion}}') | Out-Null
    if ($Image) { Invoke-LzugNative docker @('image', 'inspect', $Image) | Out-Null }
}

function Wait-LzugReady {
    param([Parameter(Mandatory)] [string]$Url, [string]$State = 'ready', [int]$TimeoutSeconds = 90)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-RestMethod "$Url/api/lifecycle" -TimeoutSec 3
            if ($response.state -eq $State -and $response.ready -eq ($State -eq 'ready')) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Runtime did not reach state=$State within ${TimeoutSeconds}s"
}

function Get-LzugImage {
    if ($env:LZUG_IMAGE) { return $env:LZUG_IMAGE }
    return 'lzug-app:0.0.0-dev.local'
}

function New-LzugFixture {
    param([string]$Directory, [string]$Image = (Get-LzugImage))
    $name = 'lzug-pester-' + [guid]::NewGuid().ToString('N')
    $fixture = @{
        Name = $name; Image = $Image; Data = "$name-data"; Work = "$name-work"; Socket = "$name-socket"
        Container = ''; Url = ''; Directory = $Directory
        Compose = @('compose', '--project-name', $name, '--env-file', "$Directory/compose.env", '-f', 'compose.yaml', '-f', "$Directory/socket.yaml")
    }
    New-Item -ItemType Directory -Path "$Directory/admin" -Force | Out-Null
    @"
LZUG_IMAGE=$($fixture.Image)
LZUG_DATA_VOLUME=$($fixture.Data)
LZUG_HOST_PORT=0
LZUG_ADMIN_SOCKET_DIR=$Directory/admin
"@ | Set-Content "$Directory/compose.env"
    # Keep POSIX ownership inside the engine, including Docker Desktop's VM.
    # Only the disposable socket mount differs from the published Compose service.
    @"
services:
  lzug:
    volumes:
      - type: volume
        source: contract_socket
        target: /run/lzug-admin
        volume:
          nocopy: true
volumes:
  contract_socket:
    name: $name-socket
"@ | Set-Content "$Directory/socket.yaml"
    return $fixture
}

function Invoke-LzugCompose {
    param($Fixture, [string[]]$Arguments)
    # Never let a developer's deployment variables select real data or socket paths.
    $saved = @(Get-ChildItem Env: | Where-Object Name -Like 'LZUG_*')
    try {
        foreach ($variable in $saved) { Remove-Item "Env:$($variable.Name)" }
        Invoke-LzugNative docker ($Fixture.Compose + $Arguments)
    } finally {
        foreach ($variable in $saved) { Set-Item "Env:$($variable.Name)" $variable.Value }
    }
}

function Initialize-LzugFixture {
    param($Fixture, [switch]$Legacy)
    Assert-LzugDocker -Image $Fixture.Image
    # Root is restricted to preparation of this disposable socket directory.
    Invoke-LzugCompose $Fixture @('run', '--rm', '--no-deps', '--user', '0:0', '--cap-add', 'CHOWN', '--cap-add', 'FOWNER', '--entrypoint', 'sh', 'lzug', '-c', 'chown 10001:10001 /run/lzug-admin && chmod 0750 /run/lzug-admin') | Out-Null
    Invoke-LzugNative docker @('volume', 'create', $Fixture.Work) | Out-Null
    Invoke-LzugNative docker @('run', '--rm', '--network', 'none', '--read-only', '--user', '0:0', '--cap-drop', 'ALL', '--cap-add', 'CHOWN', '--mount', "type=volume,source=$($Fixture.Work),target=/work,volume-nocopy", '--entrypoint', 'chown', $Fixture.Image, '10002:10001', '/work') | Out-Null
    if (-not $Legacy) {
        Invoke-LzugCompose $Fixture @('run', '--rm', '--no-deps', '--entrypoint', 'python', 'lzug', '-c', 'from backend.persistence.database import initialize; initialize()') | Out-Null
    }
}

function Start-LzugFixture {
    param($Fixture, [string]$State = 'ready')
    Invoke-LzugCompose $Fixture @('up', '-d') | Out-Null
    $Fixture.Container = (Invoke-LzugCompose $Fixture @('ps', '-q', 'lzug')).Trim()
    Update-LzugUrl $Fixture
    Wait-LzugReady $Fixture.Url -State $State
}

function Update-LzugUrl {
    param($Fixture)
    $binding = (Invoke-LzugCompose $Fixture @('port', 'lzug', '8000')).Trim()
    $Fixture.Url = 'http://127.0.0.1:' + ($binding -split ':')[-1]
}

function Remove-LzugFixture {
    param($Fixture)
    if ($null -eq $Fixture) { return }
    # Attempt every cleanup even when setup or an assertion failed.
    $failures = @()
    foreach ($arguments in @(
        ($Fixture.Compose + @('down', '--volumes', '--remove-orphans')),
        @('volume', 'rm', '--force', $Fixture.Work)
    )) {
        try { Invoke-LzugNative docker $arguments | Out-Null } catch { $failures += $_ }
    }
    if ($failures.Count) { throw "Fixture cleanup failed for $($Fixture.Name): $($failures.Count) operations" }
}

function Invoke-LzugCli {
    param($Fixture, [string[]]$Arguments, [int]$ExpectedExit = 0, [string]$InputText)
    # The delivered binary sees the server PID, but cannot mount backend data.
    $native = @('run', '--rm', '-i', '--network', 'none', '--read-only', '--user', '10002:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--mount', "type=volume,source=$($Fixture.Work),target=/work,volume-nocopy", '--workdir', '/work')
    if ($Fixture.Container) {
        $native += @('--pid', "container:$($Fixture.Container)", '--mount', "type=volume,source=$($Fixture.Socket),target=/run/lzug-admin,readonly,volume-nocopy")
    }
    $native += @('--entrypoint', '/usr/local/bin/lzug-admin', $Fixture.Image, '--endpoint', 'unix:///run/lzug-admin/admin.sock', '--json') + $Arguments
    $output = Invoke-LzugNative docker $native -ExpectedExit $ExpectedExit -InputText $InputText
    $payload = $output | ConvertFrom-Json
    $payload.exit_code | Should -Be $ExpectedExit
    $payload.ok | Should -Be ($ExpectedExit -eq 0)
    $payload.schema_version | Should -Be 1
    return $payload
}

function Assert-LzugRuntime {
    param($Fixture)
    Invoke-LzugNative docker @('exec', $Fixture.Container, 'python', '-c', @'
import errno, os, stat
from pathlib import Path
assert (os.geteuid(), os.getegid()) == (10001, 10001)
for path, kind, mode in (
    (Path('/run/lzug-admin'), stat.S_ISDIR, 0o750),
    (Path('/run/lzug-admin/admin.sock'), stat.S_ISSOCK, 0o660),
):
    info = path.lstat()
    assert kind(info.st_mode)
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (10001, 10001, mode)
try:
    Path('/app/forbidden-write').write_text('must fail')
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise AssertionError('root filesystem is writable')
'@) | Out-Null
    Invoke-LzugNative docker @('exec', $Fixture.Container, 'python', '-m', 'backend.healthcheck') | Out-Null
}

function Assert-LzugPersistedCommittee {
    param($Fixture, [string[]]$Bootstrap)
    $replayed = Invoke-LzugCli $Fixture $Bootstrap
    $replayed.result.replayed | Should -BeTrue -Because 'the previously committed bootstrap must survive the lifecycle transition'
    return $replayed.result
}
