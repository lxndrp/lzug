BeforeAll {
    . (Join-Path $PSScriptRoot 'LzugHarness.ps1')
}

Describe 'delivered operator CLI on the product runtime' {
    BeforeAll {
        $fixture = New-LzugFixture "$TestDrive/operator"
        Initialize-LzugFixture $fixture
        Start-LzugFixture $fixture
    }
    AfterAll { Remove-LzugFixture $fixture }

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
}
