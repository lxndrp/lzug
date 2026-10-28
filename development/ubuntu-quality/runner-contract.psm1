Set-StrictMode -Version Latest

function Test-LzugWorktreeScope {
    param([Parameter(Mandatory)][string]$Scope)

    return $Scope -cmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$'
}

function Test-LzugLocalDockerEndpoint {
    param(
        [Parameter(Mandatory)][string]$Endpoint,
        [Parameter(Mandatory)][string]$SocketPath
    )

    if (-not $Endpoint.StartsWith('unix://', [StringComparison]::Ordinal)) {
        return $false
    }

    $endpointPath = $Endpoint.Substring('unix://'.Length)
    if (-not [IO.Path]::IsPathRooted($endpointPath)) {
        return $false
    }

    try {
        $endpointItem = Get-Item -LiteralPath $endpointPath -Force -ErrorAction Stop
        $socketItem = Get-Item -LiteralPath $SocketPath -Force -ErrorAction Stop
        $endpointTarget = $endpointItem.ResolveLinkTarget($true)
        $socketTarget = $socketItem.ResolveLinkTarget($true)
        $resolvedEndpoint = if ($endpointTarget) { $endpointTarget.FullName } else { $endpointItem.FullName }
        $resolvedSocket = if ($socketTarget) { $socketTarget.FullName } else { $socketItem.FullName }

        return [string]::Equals(
            [IO.Path]::GetFullPath($resolvedEndpoint),
            [IO.Path]::GetFullPath($resolvedSocket),
            [StringComparison]::Ordinal
        )
    }
    catch {
        return $false
    }
}

function Test-LzugRunnerContainerOwnership {
    param(
        [Parameter(Mandatory)][string]$ContainerName,
        [Parameter(Mandatory)][string]$ContainerPrefix,
        [Parameter(Mandatory)][string]$ResourceLabel,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Labels
    )

    $expectedName = '^' + [regex]::Escape($ContainerPrefix) + '-[0-9]+$'
    return ($ContainerName -cmatch $expectedName) -and $Labels.Contains($ResourceLabel)
}

function Get-LzugQualityImageReferences {
    param([Parameter(Mandatory)][string]$ResourcePrefix)

    return @{
        App = "$ResourcePrefix-product:0.0.0-dev.local"
        Contract = "$ResourcePrefix-product:0.0.0-rc.0-contract"
        DemoApp = "$ResourcePrefix-demo-app:local"
        DemoSeed = "$ResourcePrefix-demo-seed:local"
    }
}

function Test-LzugBuilderOwnership {
    param(
        [Parameter(Mandatory)][string]$BuilderName,
        [Parameter(Mandatory)][string]$ExpectedBuilderName
    )

    return [string]::Equals($BuilderName, $ExpectedBuilderName, [StringComparison]::Ordinal)
}

function Complete-LzugRunnerOutcome {
    param(
        [AllowNull()][System.Management.Automation.ErrorRecord]$TaskError,
        [string[]]$CleanupErrors = @()
    )

    if ($TaskError) {
        foreach ($cleanupError in $CleanupErrors) {
            [Console]::Error.WriteLine("Ubuntu quality cleanup also failed: $cleanupError")
        }
        throw $TaskError
    }

    if ($CleanupErrors.Count -gt 0) {
        throw "Ubuntu quality cleanup failed: $($CleanupErrors -join '; ')"
    }
}

Export-ModuleMember -Function Test-LzugWorktreeScope, Test-LzugLocalDockerEndpoint, Test-LzugRunnerContainerOwnership, Get-LzugQualityImageReferences, Test-LzugBuilderOwnership, Complete-LzugRunnerOutcome
