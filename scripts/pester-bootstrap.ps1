function Save-PinnedPesterModule {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version,
        [Parameter(Mandatory)]
        [string]$Path,
        [ValidateRange(1, 5)]
        [int]$MaxAttempts = 3
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Save-PSResource -Name Pester -Version $Version -Repository PSGallery -Path $Path -TrustRepository -Quiet -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq $MaxAttempts) { throw }

            Write-Warning ('PowerShell Gallery failed to provide Pester {0} on attempt {1}/{2}: {3}. Retrying.' -f $Version, $attempt, $MaxAttempts, $_.Exception.Message)
            Start-Sleep -Seconds $attempt
        }
    }
}
