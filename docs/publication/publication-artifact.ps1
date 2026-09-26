[CmdletBinding()]
param(
    [switch]$CheckReproducibility,
    [string]$ChangedFiles,
    [string]$Runs,
    [string]$Artifacts,
    [string]$Revision,
    [string]$Now
)

function Get-JsonRecords {
    param(
        [Parameter(Mandatory)]$Payload,
        [Parameter(Mandatory)][string]$Key
    )

    $pages = @($Payload)
    $records = foreach ($page in $pages) {
        if ($page -is [System.Collections.IDictionary] -and $page[$Key] -is [array]) {
            foreach ($item in $page[$Key]) {
                if ($item -is [System.Collections.IDictionary]) { $item }
            }
        }
    }
    @($records)
}

function Get-ReusablePublicationRun {
    param(
        [Parameter(Mandatory)]$RunsPayload,
        [Parameter(Mandatory)]$ArtifactsPayload,
        [Parameter(Mandatory)][string]$Revision,
        [Parameter(Mandatory)][datetimeoffset]$Now
    )

    $successfulRuns = @{}
    foreach ($run in (Get-JsonRecords -Payload $RunsPayload -Key 'workflow_runs')) {
        if ([string]$run.head_sha -ine $Revision -or
            $run.head_branch -ne 'master' -or
            $run.status -ne 'completed' -or
            $run.conclusion -ne 'success' -or
            $run.event -notin @('push', 'workflow_dispatch', 'schedule')) {
            continue
        }
        $successfulRuns[[string]$run.id] = $run
    }

    $candidates = foreach ($artifact in (Get-JsonRecords -Payload $ArtifactsPayload -Key 'artifacts')) {
        $runId = [string]$artifact.workflow_run.id
        $size = 0L
        if ($artifact.name -ne 'lzug-public-site' -or
            -not $successfulRuns.ContainsKey($runId) -or
            $artifact.expired -ne $false -or
            -not [long]::TryParse([string]$artifact.size_in_bytes, [ref]$size) -or
            $size -le 0) {
            continue
        }
        $created = [datetimeoffset]::MinValue
        $expires = [datetimeoffset]::MinValue
        if (-not [datetimeoffset]::TryParse([string]$artifact.created_at, [ref]$created) -or
            -not [datetimeoffset]::TryParse([string]$artifact.expires_at, [ref]$expires) -or
            $created -gt $Now -or $expires -le $Now) {
            continue
        }
        [pscustomobject]@{ Created = $created; RunId = $runId }
    }
    $newest = @($candidates | Sort-Object Created -Descending | Select-Object -First 1)
    if ($newest.Count -eq 0) { return $null }
    $newest[0].RunId
}

$script:ReproducibilityInputs = @(
    '.github/workflows/publication.yml', '.mise.toml', '.python-version',
    'Taskfile.yml', 'backend/fastapi_assembly.py', 'frontend/.node-version',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/tsconfig',
    'frontend/tsconfig.app.json', 'docs/publication/hugo.toml',
    'docs/publication/go.mod', 'docs/publication/go.sum', 'pyproject.toml',
    'uv.lock', 'docs/publication/publication-artifact.ps1'
)

function Test-PublicationReproducibility {
    param([string[]]$Paths)

    foreach ($path in $Paths) {
        if (($path.StartsWith('docs/publication/') -and
                -not $path.StartsWith('docs/publication/content/')) -or
            $script:ReproducibilityInputs -contains $path -or
            ($path.StartsWith('frontend/tsconfig') -and $path.EndsWith('.json'))) {
            return $true
        }
    }
    $false
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    if ($CheckReproducibility) {
        $paths = if ($ChangedFiles) { @(Get-Content -LiteralPath $ChangedFiles) } else { @() }
        if (Test-PublicationReproducibility -Paths $paths) { 'true' } else { 'false' }
        exit 0
    }
    if (-not ($Runs -and $Artifacts -and $Revision -and $Now)) {
        throw 'Artifact selection requires -Runs, -Artifacts, -Revision, and -Now.'
    }
    $nowValue = [datetimeoffset]::MinValue
    if (-not [datetimeoffset]::TryParse($Now, [ref]$nowValue)) {
        throw '-Now must be an ISO-8601 timestamp.'
    }
    $runsPayload = Get-Content -Raw -LiteralPath $Runs | ConvertFrom-Json -AsHashtable
    $artifactsPayload = Get-Content -Raw -LiteralPath $Artifacts | ConvertFrom-Json -AsHashtable
    $runId = Get-ReusablePublicationRun -RunsPayload $runsPayload -ArtifactsPayload $artifactsPayload -Revision $Revision -Now $nowValue
    if ($runId) { $runId }
}
