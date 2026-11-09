BeforeAll {
    . (Join-Path $PSScriptRoot '../../scripts/pester-bootstrap.ps1')
}

Describe 'Pester module bootstrap' {
    It 'retries a transient gallery failure' {
        $script:saveAttempts = 0
        Mock Save-PSResource {
            $script:saveAttempts++
            if ($script:saveAttempts -eq 1) { throw 'Temporary Gallery failure' }
        }
        Mock Start-Sleep {}

        Save-PinnedPesterModule -Version '5.7.1' -Path 'module-cache'

        Should -Invoke Save-PSResource -Times 2 -Exactly
        Should -Invoke Start-Sleep -Times 1 -Exactly
    }

    It 'fails after the configured number of attempts' {
        Mock Save-PSResource { throw 'Gallery unavailable' }
        Mock Start-Sleep {}

        { Save-PinnedPesterModule -Version '5.7.1' -Path 'module-cache' -MaxAttempts 3 } | Should -Throw '*Gallery unavailable*'

        Should -Invoke Save-PSResource -Times 3 -Exactly
        Should -Invoke Start-Sleep -Times 2 -Exactly
    }
}
