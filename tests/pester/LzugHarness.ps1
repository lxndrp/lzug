Set-StrictMode -Version Latest

function Invoke-LzugNative {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [string[]]$Arguments
    )
    $output = & $Command @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE`n$($output -join "`n")"
    }
    $output
}

function Assert-LzugDocker {
    param([string]$Image)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Set-ItResult -Skipped -Because 'Docker is unavailable.'
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Set-ItResult -Skipped -Because 'Docker engine is unavailable.'
    }
    if ($Image) {
        & docker image inspect $Image *> $null
        if ($LASTEXITCODE -ne 0) {
            Set-ItResult -Skipped -Because "Docker image $Image is unavailable."
        }
    }
}

function Wait-LzugReady {
    param([Parameter(Mandatory)] [string]$Url, [int]$TimeoutSeconds = 90)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-RestMethod "$Url/api/ready" -TimeoutSec 5
            if ($response.ready -eq $true -and $response.state -eq 'ready') { return }
        } catch { }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Runtime did not become ready: $Url"
}

function Get-LzugImage {
    if ($env:LZUG_IMAGE) { return $env:LZUG_IMAGE }
    return 'lzug-app:0.0.0-dev.local'
}
