# Stops a commit that would put a client, a colleague or personal data into this shared repo.
#
# The git pre-commit hook in hooks\ runs it on the staged lines; install.ps1 turns the hook on.
#   & <repo folder>\check-no-clients.ps1          staged lines only (what the hook checks)
#   & <repo folder>\check-no-clients.ps1 -All     every tracked file, for an audit
#
# Two kinds of patterns:
#   general patterns below: e-mail addresses, personal Windows paths and token formats; nothing about any client.
#   %USERPROFILE%\.claude\denylist.txt: your own clients, colleagues, repos, ticket keys and accounts, one
#   case-insensitive regex per line, # for comments. It stays on your machine; without it only the general patterns run.
# Runs in Windows PowerShell 5.1 and PowerShell 7.

param(
    [switch] $All,
    [string] $DenylistPath = (Join-Path $env:USERPROFILE '.claude\denylist.txt')
)

$ErrorActionPreference = 'Stop'

$GENERAL_PATTERNS = @(
    '[A-Za-z0-9._%+-]+@(?!example\.|users\.noreply\.github\.com)[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,}',
    '[A-Za-z]:[\\/]+Users[\\/]+(?![<%$]|\.\.\.|me[\\/]|name[\\/]|user[\\/]|Public[\\/]|Default[\\/])[A-Za-z0-9._-]+',
    'gh[pousr]_[A-Za-z0-9]{30,}',
    'github_pat_[A-Za-z0-9_]{30,}',
    'ATATT[A-Za-z0-9_=-]{30,}',
    'AKIA[0-9A-Z]{16}'
)
$IGNORED_EMAIL_PREFIXES = @('git@')

function Get-DenylistPatterns
{
    if (-not (Test-Path -LiteralPath $DenylistPath))
    {
        Write-Host "No $DenylistPath; checking only the general patterns (e-mail addresses, personal paths, tokens)."
        return @()
    }

    return @(Get-Content -LiteralPath $DenylistPath -Encoding UTF8 |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') })
}

function Get-StagedLines
{
    $repositoryRoot = git rev-parse --show-toplevel
    $lines = @()
    $currentPath = $null
    $lineNumber = 0

    foreach ($diffLine in git -C $repositoryRoot -c core.quotepath=off diff --cached -U0 --no-color --diff-filter=ACMR)
    {
        if ($diffLine -match '^\+\+\+ b/(.+)$')
        {
            $currentPath = $Matches[1]
            $lines += [pscustomobject]@{ Path = $currentPath; Line = 0; Text = $currentPath }
            continue
        }

        if ($diffLine -match '^@@ -\S+ \+(\d+)')
        {
            $lineNumber = [int]$Matches[1]
            continue
        }

        $isAddedLine = $currentPath -and $diffLine.StartsWith('+') -and -not $diffLine.StartsWith('+++')
        if ($isAddedLine)
        {
            $lines += [pscustomobject]@{ Path = $currentPath; Line = $lineNumber; Text = $diffLine.Substring(1) }
            $lineNumber++
        }
    }

    return $lines
}

function Get-TrackedLines
{
    $repositoryRoot = git rev-parse --show-toplevel
    $lines = @()

    foreach ($relativePath in git -C $repositoryRoot -c core.quotepath=off ls-files)
    {
        $lines += [pscustomobject]@{ Path = $relativePath; Line = 0; Text = $relativePath }
        $fullPath = Join-Path $repositoryRoot $relativePath
        $lineNumber = 0

        foreach ($text in Get-Content -LiteralPath $fullPath -Encoding UTF8)
        {
            $lineNumber++
            $lines += [pscustomobject]@{ Path = $relativePath; Line = $lineNumber; Text = $text }
        }
    }

    return $lines
}

function Find-Hits
{
    param(
        [object[]] $Lines,
        [string[]] $Patterns
    )

    foreach ($line in $Lines)
    {
        foreach ($pattern in $Patterns)
        {
            foreach ($match in [regex]::Matches($line.Text, $pattern, 'IgnoreCase'))
            {
                $isIgnoredEmail = $IGNORED_EMAIL_PREFIXES | Where-Object { $match.Value.StartsWith($_) }
                if ($isIgnoredEmail) { continue }

                [pscustomobject]@{ Path = $line.Path; Line = $line.Line; Found = $match.Value }
            }
        }
    }
}

$patterns = @($GENERAL_PATTERNS) + @(Get-DenylistPatterns)
$lines = if ($All) { Get-TrackedLines } else { Get-StagedLines }
$hits = @(Find-Hits -Lines $lines -Patterns $patterns)

if ($hits.Count -eq 0)
{
    exit 0
}

Write-Host 'Commit stopped: this looks like data about a client, a colleague or you.'
foreach ($hit in $hits)
{
    $location = if ($hit.Line) { "$($hit.Path):$($hit.Line)" } else { "$($hit.Path) (file name)" }
    Write-Host "  $location  $($hit.Found)"
}
Write-Host 'Replace it with an invented example or move it to a local file. If it is a false alarm, narrow the pattern in the denylist.'
exit 1
