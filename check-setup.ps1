# Says what this machine still needs for the rules and skills in this repo to work.
# Changes nothing. install.ps1 runs it at the end; run it on its own any time:
#   & <repo folder>\check-setup.ps1

$ErrorActionPreference = 'Stop'

$repositoryRoot = $PSScriptRoot
$PR_REVIEW_CONFIG_PATH = "$repositoryRoot\skills\pr-review\config.local.ps1"
$DENYLIST_PATH = "$env:USERPROFILE\.claude\denylist.txt"
$BITBUCKET_API = 'https://api.bitbucket.org/2.0'
$HTTP_TIMEOUT_SECONDS = 15

[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

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

    if (Test-Command 'pwsh') { Write-Status -Status 'ok' -Message 'pwsh (PowerShell 7)' }
    else { Write-Status -Status 'missing' -Message 'pwsh (PowerShell 7): pr-review and pr-walkthrough run their scripts with it (winget install Microsoft.PowerShell)' }

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

function Get-BasicAuthorization
{
    param(
        [string] $User,
        [string] $Secret
    )

    return 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${User}:$Secret"))
}

function Get-HttpStatus
{
    param(
        [string] $Uri,
        [string] $Authorization
    )

    try
    {
        Invoke-RestMethod -Uri $Uri -Headers @{ Authorization = $Authorization } -TimeoutSec $HTTP_TIMEOUT_SECONDS | Out-Null
        return 200
    }
    catch
    {
        $response = $_.Exception.Response
        if ($response) { return [int]$response.StatusCode }
        return 0
    }
}

function Get-AccessProblem
{
    param(
        [int] $Status
    )

    switch ($Status)
    {
        200 { return $null }
        0 { return 'the server cannot be reached (VPN or network?)' }
        401 { return 'the login is refused (401): wrong e-mail or token, or the token expired' }
        403 { return 'the token is missing a permission (403)' }
        404 { return 'the repo is not found or the token cannot see it (404)' }
        default { return "the server answered $Status" }
    }
}

function Test-GithubRepository
{
    param(
        [string] $Name,
        [hashtable] $Repository
    )

    $hasOwnAccount = [bool]$Repository.ghAccount
    $accountWorks = (-not $hasOwnAccount) -or (Test-CommandSucceeds { gh auth token --user $Repository.ghAccount })

    if (-not $accountWorks)
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: gh account '$($Repository.ghAccount)' is not logged in (gh auth login)"
        return
    }

    $originalToken = $env:GH_TOKEN
    if ($hasOwnAccount) { $env:GH_TOKEN = gh auth token --user $Repository.ghAccount }
    $repoVisible = Test-CommandSucceeds { gh api "repos/$($Repository.owner)/$Name" }
    $env:GH_TOKEN = $originalToken

    if ($repoVisible) { Write-Status -Status 'ok' -Message "pr-review $Name (GitHub)" }
    else { Write-Status -Status 'missing' -Message "pr-review ${Name}: the gh account cannot see $($Repository.owner)/$Name" }
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

    $email = Get-UserEnvironmentValue "${prefix}_EMAIL"

    if (-not $email.Contains('@'))
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: ${prefix}_EMAIL must be the e-mail of your Atlassian account, not a user name"
        return
    }

    $authorization = Get-BasicAuthorization -User $email -Secret (Get-UserEnvironmentValue "${prefix}_TOKEN")
    $problem = Get-AccessProblem (Get-HttpStatus -Uri "$BITBUCKET_API/repositories/$($Repository.workspace)/$Name" -Authorization $authorization)

    if ($problem)
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: $problem"
        return
    }

    Write-Status -Status 'ok' -Message "pr-review $Name (Bitbucket)"

    if (-not (Get-UserEnvironmentValue "${prefix}_TOKEN_WRITE"))
    {
        Write-Status -Status 'note' -Message "pr-review ${Name}: no ${prefix}_TOKEN_WRITE, so comments cannot be posted, only drafted"
    }
}

function Test-AzureRepository
{
    param(
        [string] $Name,
        [hashtable] $Repository
    )

    $tokenVariable = $Repository.tokenVariable

    if (-not $tokenVariable)
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: no tokenVariable in config.local.ps1 (the environment variable that holds the Azure DevOps PAT)"
        return
    }

    if (-not (Get-UserEnvironmentValue $tokenVariable))
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: environment variable $tokenVariable is not set (see skills\pr-review\README.md)"
        return
    }

    $authorization = Get-BasicAuthorization -User '' -Secret (Get-UserEnvironmentValue $tokenVariable)
    $repositoryApi = '{0}/{1}/_apis/git/repositories/{2}?api-version=6.0' -f $Repository.azureUrl, [uri]::EscapeDataString($Repository.project), [uri]::EscapeDataString($Name)
    $problem = Get-AccessProblem (Get-HttpStatus -Uri $repositoryApi -Authorization $authorization)

    if ($problem)
    {
        Write-Status -Status 'missing' -Message "pr-review ${Name}: $problem"
        return
    }

    Write-Status -Status 'ok' -Message "pr-review $Name (Azure DevOps)"
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

        switch ($repository.host)
        {
            'bitbucket' { Test-BitbucketRepository -Name $name -Repository $repository }
            'azure' { Test-AzureRepository -Name $name -Repository $repository }
            default { Test-GithubRepository -Name $name -Repository $repository }
        }

        $isJavaScriptProject = Test-Path -LiteralPath (Join-Path $repository.localPath 'package.json')

        if ($isJavaScriptProject -and -not (Test-Command 'node'))
        {
            Write-Status -Status 'note' -Message "pr-review ${name}: a JavaScript project, but Node.js is missing, so its build and tests cannot run"
        }
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
