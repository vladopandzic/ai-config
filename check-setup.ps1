# Says what this machine still needs for the rules and skills in this repo to work.
# Changes nothing. install.ps1 runs it at the end; run it on its own any time:
#   & <repo folder>\check-setup.ps1

$ErrorActionPreference = 'Stop'

$repositoryRoot = $PSScriptRoot
$PR_REVIEW_CONFIG_PATH = "$repositoryRoot\skills\pr-review\config.local.ps1"
$DENYLIST_PATH = "$env:USERPROFILE\.claude\denylist.txt"

function Write-Status
{
    param(
        [string] $Status,
        [string] $Message
    )

    Write-Host ('{0,-9}{1}' -f $Status, $Message)
}

function Test-Command
{
    param(
        [string] $Name
    )

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-CommandSucceeds
{
    param(
        [scriptblock] $Command
    )

    try
    {
        & $Command *> $null
        return $LASTEXITCODE -eq 0
    }
    catch
    {
        return $false
    }
}

function Get-UserEnvironmentValue
{
    param(
        [string] $Name
    )

    $value = [Environment]::GetEnvironmentVariable($Name)

    if (-not $value)
    {
        $value = [Environment]::GetEnvironmentVariable($Name, 'User')
    }

    return $value
}

function Test-Tools
{
    if (Test-Command 'git') { Write-Status -Status 'ok' -Message 'git' }
    else { Write-Status -Status 'missing' -Message 'git: everything needs it (https://git-scm.com)' }

    if (-not (Test-Command 'gh'))
    {
        Write-Status -Status 'missing' -Message 'gh (GitHub CLI): pr-review needs it for GitHub repos (winget install GitHub.cli)'
    }
    elseif (Test-CommandSucceeds { gh auth status })
    {
        Write-Status -Status 'ok' -Message 'gh, logged in'
    }
    else
    {
        Write-Status -Status 'missing' -Message 'gh is not logged in: run gh auth login'
    }

    if (Test-CommandSucceeds { python -c 'import sys' })
    {
        Write-Status -Status 'ok' -Message 'python'
    }
    else
    {
        Write-Status -Status 'missing' -Message 'python: /self-improve history needs it (winget install Python.Python.3.12)'
    }

    if (Test-Command 'dotnet') { Write-Status -Status 'ok' -Message 'dotnet' }
    else { Write-Status -Status 'missing' -Message 'dotnet SDK: ef-migration, prepare-pr and release need it' }

    if (Test-CommandSucceeds { docker info }) { Write-Status -Status 'ok' -Message 'docker, running' }
    else { Write-Status -Status 'note' -Message 'docker is not running: prepare-pr skips integration tests that need it' }
}

function Test-GithubRepository
{
    param(
        [string] $Name,
        [hashtable] $Repository
    )

    $hasOwnAccount = [bool]$Repository.ghAccount
    $accountWorks = (-not $hasOwnAccount) -or (Test-CommandSucceeds { gh auth token --user $Repository.ghAccount })

    if ($accountWorks)
    {
        Write-Status -Status 'ok' -Message "pr-review $Name (GitHub)"
        return
    }

    Write-Status -Status 'missing' -Message "pr-review ${Name}: gh account '$($Repository.ghAccount)' is not logged in (gh auth login)"
}

function Test-BitbucketRepository
{
    param(
        [string] $Name,
        [hashtable] $Repository
    )

    $prefix = 'BITBUCKET_' + ($Repository.workspace.ToUpper() -replace '[^A-Z0-9]', '_')
    $missingVariables = @("${prefix}_EMAIL", "${prefix}_TOKEN") | Where-Object { -not (Get-UserEnvironmentValue $_) }

    if ($missingVariables)
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: environment variables $($missingVariables -join ', ') (see skills\pr-review\README.md)"
        return
    }

    Write-Status -Status 'ok' -Message "pr-review $Name (Bitbucket)"

    if (-not (Get-UserEnvironmentValue "${prefix}_TOKEN_WRITE"))
    {
        Write-Status -Status 'note' -Message "pr-review ${Name}: no ${prefix}_TOKEN_WRITE, so comments cannot be posted, only drafted"
    }
}

function Test-PrReviewSetup
{
    if (-not (Test-Path -LiteralPath $PR_REVIEW_CONFIG_PATH))
    {
        Write-Status -Status 'missing' -Message 'pr-review does not know your repos yet: tell Claude "/pr-review postavi" and it writes the list for you'
        return
    }

    . $PR_REVIEW_CONFIG_PATH

    foreach ($name in $ReviewRepos.Keys | Sort-Object)
    {
        $repository = $ReviewRepos[$name]
        $hasLocalClone = $repository.localPath -and (Test-Path -LiteralPath $repository.localPath)

        if (-not $hasLocalClone)
        {
            Write-Status -Status 'missing' -Message "pr-review ${name}: no local clone at '$($repository.localPath)'"
            continue
        }

        if ($repository.host -eq 'bitbucket') { Test-BitbucketRepository -Name $name -Repository $repository }
        else { Test-GithubRepository -Name $name -Repository $repository }
    }
}

function Test-Denylist
{
    if (Test-Path -LiteralPath $DENYLIST_PATH) { Write-Status -Status 'ok' -Message $DENYLIST_PATH }
    else { Write-Status -Status 'note' -Message "no ${DENYLIST_PATH}: commits here are checked only for e-mails, tokens and personal paths" }
}

Test-Tools
Test-PrReviewSetup
Test-Denylist
