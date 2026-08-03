# Setup Tab Completion for yt2md in PowerShell (Windows PowerShell 5.1 & PowerShell 7+)
# Run this script to add yt2md parameter tab completion to your PowerShell profiles.

$profiles = @(
    $PROFILE,
    "$HOME\Documents\PowerShell\Microsoft.PowerShell_profile.ps1",
    "$HOME\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
) | Select-Object -Unique

$completerScript = @'

# Tab completion for yt2md CLI
Register-ArgumentCompleter -Native -CommandName yt2md -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    $parameters = @(
        '--days', '--category', '--url', '--language', '--channel',
        '--ollama', '--cloud', '--skip-verification', '--max-videos',
        '-v', '--verbose', '-q', '--quiet', '--kindle', '--auto-generated',
        '--openrouter', '--openrouter-model', '--skip-summarize-shorts'
    )

    $categories = @('IT', 'Crypto', 'AI', 'Fitness', 'Trading', 'News')
    $languages = @('en', 'pl', 'es')

    $elements = $commandAst.CommandElements
    $prevElement = ''
    if ($elements.Count -gt 1) {
        $prevElement = $elements[-1].Extent.Text
        if ($wordToComplete -ne '' -and $elements.Count -gt 2) {
            $prevElement = $elements[-2].Extent.Text
        }
    }

    if ($prevElement -eq '--category') {
        $categories | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    }
    elseif ($prevElement -eq '--language') {
        $languages | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
    }
    else {
        $parameters | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', $_)
        }
    }
}
'@

foreach ($p in $profiles) {
    if (Test-Path $p) {
        $existingContent = Get-Content $p -Raw -ErrorAction SilentlyContinue
        if ($existingContent -like "*CommandName yt2md*") {
            Write-Host "yt2md tab completion already present in: $p" -ForegroundColor Yellow
        } else {
            Add-Content -Path $p -Value "`n$completerScript"
            Write-Host "✅ Added yt2md tab completion to $p" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "To enable it in your current terminal session, run:" -ForegroundColor Cyan
Write-Host "    . `$PROFILE" -ForegroundColor White
