<#
  pr-common.ps1 — shared by pr-harvest.ps1 and pr-post.ps1: loads config.local.ps1 and talks to GitHub, Bitbucket or Azure DevOps.

  GitHub:    gh CLI. A repo's ghAccount is used through GH_TOKEN for this process only; the active gh account is not switched.
  Bitbucket: API token with scopes, Basic auth email:token, from environment variables (process first, then User scope):
               BITBUCKET_<WORKSPACE>_EMAIL
               BITBUCKET_<WORKSPACE>_TOKEN         read:user:bitbucket, read:repository:bitbucket, read:pullrequest:bitbucket
               BITBUCKET_<WORKSPACE>_TOKEN_WRITE   write:pullrequest:bitbucket (only for posting)
             <WORKSPACE> = workspace upper-cased, every non-alphanumeric character replaced with '_'.
  Azure DevOps: cloud (https://dev.azure.com/<org>) or Server (https://<server>/<collection>), same REST API.
             Personal access token in the environment variable the repo's tokenVariable names (process first, then User scope),
             Basic auth with an empty user. Scope Code (Read); Code (Read & write) only for posting.
             The PR diff is computed locally from the fetched branches.
#>

$SKILL_ROOT = Split-Path $PSScriptRoot -Parent
$LOCAL_CONFIG_PATH = Join-Path $SKILL_ROOT 'config.local.ps1'
$BITBUCKET_API = 'https://api.bitbucket.org/2.0'
$DEFAULT_TICKET_REGEX = '\b[A-Z][A-Z0-9]+-\d+\b'
$AZURE_API_VERSION = '6.0'
$AZURE_POLICY_API_VERSION = '6.0-preview.1'
$AZURE_APPROVED_VOTE = 5
$AZURE_BUILD_POLICY_TYPE_ID = '0609b952-1397-4640-95ec-e00a01b2c241'
$ORIGINAL_GH_TOKEN = $env:GH_TOKEN

function Import-ReviewConfig {
  if (-not (Test-Path $LOCAL_CONFIG_PATH)) {
    return "nema ${LOCAL_CONFIG_PATH}: pokreni /pr-review postavi da se složi popis repoa"
  }
  . $LOCAL_CONFIG_PATH
  $script:ReviewRepos = $ReviewRepos
  $script:ReviewsDir = if ($ReviewsDir) { $ReviewsDir } else { Join-Path $HOME 'pr-review' }
  return $null
}

function Resolve-RepoConfig {
  param([string]$Repo)
  if (-not $Repo -and $ReviewRepos.Count -eq 1) { $Repo = @($ReviewRepos.Keys)[0] }
  if (-not $Repo -or -not $ReviewRepos.ContainsKey($Repo)) { return $null }
  $repoConfig = $ReviewRepos[$Repo]
  $hostName = if ($repoConfig.host) { $repoConfig.host } else { 'github' }
  return [pscustomobject]@{
    name        = $Repo
    host        = $hostName
    owner       = $repoConfig.owner
    workspace   = $repoConfig.workspace
    ghAccount   = $repoConfig.ghAccount
    bitbucketAccountId = $repoConfig.bitbucketAccountId
    azureUrl    = if ($repoConfig.azureUrl) { $repoConfig.azureUrl.TrimEnd('/') } else { $null }
    project     = $repoConfig.project
    tokenVariable = $repoConfig.tokenVariable
    localPath   = $repoConfig.localPath
    ticketRegex = if ($repoConfig.ticketRegex) { $repoConfig.ticketRegex } else { $DEFAULT_TICKET_REGEX }
    notesPath   = Join-Path $SKILL_ROOT "repos\$Repo.md"
  }
}

function Get-ConfigError {
  param($RepoConfig, [string]$Repo)
  if (-not $RepoConfig) { return "repo '$Repo' nije u config.local.ps1 (repoi: $(@($ReviewRepos.Keys) -join ', '))" }
  $name = $RepoConfig.name
  switch ($RepoConfig.host) {
    'github' { if (-not $RepoConfig.owner) { return "repo '$name' na GitHubu treba owner u config.local.ps1" } }
    'bitbucket' { if (-not $RepoConfig.workspace) { return "repo '$name' na Bitbucketu treba workspace u config.local.ps1" } }
    'azure' {
      $missingFields = @('azureUrl', 'project', 'tokenVariable') | Where-Object { -not $RepoConfig.$_ }
      if ($missingFields) { return "repo '$name' na Azure DevOpsu treba $($missingFields -join ', ') u config.local.ps1" }
    }
    default { return "repo '$name': nepoznat host '$($RepoConfig.host)' (github, bitbucket ili azure)" }
  }
  return $null
}

function Use-GhAccount {
  param([string]$Account)
  $env:GH_TOKEN = $ORIGINAL_GH_TOKEN
  if (-not $Account) { return }
  $token = (& gh auth token --user $Account 2>$null)
  if ($LASTEXITCODE -eq 0 -and $token) { $env:GH_TOKEN = $token }
}

function Get-EnvironmentValue {
  param([string]$Name)
  $value = [Environment]::GetEnvironmentVariable($Name)
  if (-not $value -and $IsWindows) { $value = [Environment]::GetEnvironmentVariable($Name, 'User') }
  return $value
}

function Get-BitbucketVariablePrefix {
  param([string]$Workspace)
  return 'BITBUCKET_' + ($Workspace.ToUpper() -replace '[^A-Z0-9]', '_')
}

function Get-BitbucketHeaders {
  param([string]$Workspace, [switch]$Write)
  $prefix = Get-BitbucketVariablePrefix $Workspace
  $tokenName = if ($Write) { "${prefix}_TOKEN_WRITE" } else { "${prefix}_TOKEN" }
  $email = Get-EnvironmentValue "${prefix}_EMAIL"
  $token = Get-EnvironmentValue $tokenName
  if (-not $email -or -not $token) { return $null }
  $credentials = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${email}:${token}"))
  return @{ Authorization = "Basic $credentials" }
}

function Invoke-Bitbucket {
  param([hashtable]$Headers, [string]$Path, [string]$Method = 'Get', $Body, [switch]$Raw)
  $uri = if ($Path -match '^https://') { $Path } else { "$BITBUCKET_API/$Path" }
  $request = @{ Uri = $uri; Headers = $Headers; Method = $Method; PreserveAuthorizationOnRedirect = $true }
  if ($null -ne $Body) {
    $request.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 8))
    $request.ContentType = 'application/json; charset=utf-8'
  }
  if ($Raw) { return (Invoke-WebRequest @request).Content }
  return Invoke-RestMethod @request
}

function Get-BitbucketPages {
  param([hashtable]$Headers, [string]$Path)
  $values = @()
  $next = $Path
  while ($next) {
    $page = Invoke-Bitbucket -Headers $Headers -Path $next
    $values += @($page.values)
    $next = $page.next
  }
  return $values
}

function Get-AzureHeaders {
  param([string]$TokenVariable)
  $token = if ($TokenVariable) { Get-EnvironmentValue $TokenVariable } else { $null }
  if (-not $token) { return $null }
  $credentials = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(":$token"))
  return @{ Authorization = "Basic $credentials" }
}

function Get-AzureRepositoryApi {
  param($RepoConfig)
  $project = [uri]::EscapeDataString($RepoConfig.project)
  $repository = [uri]::EscapeDataString($RepoConfig.name)
  return "$($RepoConfig.azureUrl)/$project/_apis/git/repositories/$repository"
}

function Invoke-Azure {
  param([hashtable]$Headers, [string]$Uri, [string]$Method = 'Get', $Body, [string]$ApiVersion = $AZURE_API_VERSION)
  $separator = if ($Uri.Contains('?')) { '&' } else { '?' }
  $request = @{ Uri = "$Uri${separator}api-version=$ApiVersion"; Headers = $Headers; Method = $Method }
  if ($null -ne $Body) {
    $request.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 8))
    $request.ContentType = 'application/json; charset=utf-8'
  }
  return Invoke-RestMethod @request
}

function Get-AzureBranchName {
  param([string]$RefName)
  return $RefName -replace '^refs/heads/', ''
}

function Get-AzureFetchSpec {
  param($PullRequest, [int]$Pr)
  return "+refs/heads/$(Get-AzureBranchName $PullRequest.sourceRefName):refs/heads/pr-$Pr"
}

function Get-AzureThreads {
  param($RepoConfig, [hashtable]$Headers, [int]$Pr)
  $threads = (Invoke-Azure -Headers $Headers -Uri "$(Get-AzureRepositoryApi $RepoConfig)/pullRequests/$Pr/threads").value
  return @($threads | Where-Object { -not $_.isDeleted })
}

function Get-AzureHumanComments {
  param($Thread)
  return @($Thread.comments | Where-Object { -not $_.isDeleted -and $_.commentType -ne 'system' -and $_.content })
}

function Get-AzureCommentId {
  param($Thread, [int]$CommentId)
  return "$($Thread.id)-$CommentId"
}

function Get-AzureThreadLine {
  param($Thread)
  $context = $Thread.threadContext
  if ($context.rightFileStart) { return $context.rightFileStart.line }
  if ($context.leftFileStart) { return $context.leftFileStart.line }
  return $null
}

function Get-AzureLocalDiff {
  param($RepoConfig, [int]$Pr, $PullRequest)
  $repoPath = $RepoConfig.localPath
  $headSha = $PullRequest.lastMergeSourceCommit.commitId
  $targetSha = $PullRequest.lastMergeTargetCommit.commitId
  git -C $repoPath fetch origin (Get-AzureFetchSpec $PullRequest $Pr) (Get-AzureBranchName $PullRequest.targetRefName) --quiet 2>$null | Out-Null
  foreach ($sha in $headSha, $targetSha) {
    git -C $repoPath cat-file -e "$sha^{commit}" 2>$null
    if ($LASTEXITCODE -ne 0) { git -C $repoPath fetch origin $sha --quiet 2>$null | Out-Null }
  }
  $mergeBase = git -C $repoPath merge-base $targetSha $headSha 2>$null
  if (-not $mergeBase) { return @() }
  $consoleEncoding = [Console]::OutputEncoding
  try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    return @(git -C $repoPath diff $mergeBase $headSha)
  } finally {
    [Console]::OutputEncoding = $consoleEncoding
  }
}

function Get-PullRequestDiff {
  param($RepoConfig, [int]$Pr, [hashtable]$Headers)
  switch ($RepoConfig.host) {
    'github' { return @(& gh pr diff $Pr -R "$($RepoConfig.owner)/$($RepoConfig.name)" 2>$null) }
    'azure' {
      $pullRequest = Invoke-Azure -Headers $Headers -Uri "$(Get-AzureRepositoryApi $RepoConfig)/pullrequests/$Pr"
      return Get-AzureLocalDiff $RepoConfig $Pr $pullRequest
    }
  }
  $diff = Invoke-Bitbucket -Headers $Headers -Path "repositories/$($RepoConfig.workspace)/$($RepoConfig.name)/pullrequests/$Pr/diff" -Raw
  return @($diff -split "`r?`n")
}
