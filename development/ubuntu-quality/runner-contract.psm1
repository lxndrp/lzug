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

Export-ModuleMember -Function Test-LzugWorktreeScope, Test-LzugLocalDockerEndpoint, Test-LzugRunnerContainerOwnership
