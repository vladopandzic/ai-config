<#
  pr-common.ps1 — shared by pr-harvest.ps1 and pr-post.ps1: loads config.local.ps1 and talks to GitHub or Bitbucket.

  GitHub:    gh CLI. A repo's ghAccount is used through GH_TOKEN for this process only; the active gh account is not switched.
  Bitbucket: API token with scopes, Basic auth email:token, from environment variables (process first, then User scope):
               BITBUCKET_<WORKSPACE>_EMAIL
               BITBUCKET_<WORKSPACE>_TOKEN         read:user:bitbucket, read:repository:bitbucket, read:pullrequest:bitbucket
               BITBUCKET_<WORKSPACE>_TOKEN_WRITE   write:pullrequest:bitbucket (only for posting)
             <WORKSPACE> = workspace upper-cased, every non-alphanumeric character replaced with '_'.
#>

$SKILL_ROOT = Split-Path $PSScriptRoot -Parent
$LOCAL_CONFIG_PATH = Join-Path $SKILL_ROOT 'config.local.ps1'
$BITBUCKET_API = 'https://api.bitbucket.org/2.0'
$DEFAULT_TICKET_REGEX = '\b[A-Z][A-Z0-9]+-\d+\b'
$ORIGINAL_GH_TOKEN = $env:GH_TOKEN

function Import-ReviewConfig {
  if (-not (Test-Path $LOCAL_CONFIG_PATH)) {
    return "nema ${LOCAL_CONFIG_PATH}: kopiraj config.example.ps1 u config.local.ps1 i upiši svoje repoe"
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
    localPath   = $repoConfig.localPath
    ticketRegex = if ($repoConfig.ticketRegex) { $repoConfig.ticketRegex } else { $DEFAULT_TICKET_REGEX }
    notesPath   = Join-Path $SKILL_ROOT "repos\$Repo.md"
  }
}

function Get-ConfigError {
  param($RepoConfig, [string]$Repo)
  if (-not $RepoConfig) { return "repo '$Repo' nije u config.local.ps1 (repoi: $(@($ReviewRepos.Keys) -join ', '))" }
  $isGithub = $RepoConfig.host -eq 'github'
  if ($isGithub -and -not $RepoConfig.owner) { return "repo '$($RepoConfig.name)' na GitHubu treba owner u config.local.ps1" }
  if (-not $isGithub -and -not $RepoConfig.workspace) { return "repo '$($RepoConfig.name)' na Bitbucketu treba workspace u config.local.ps1" }
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

function Get-PullRequestDiff {
  param($RepoConfig, [int]$Pr, [hashtable]$BitbucketHeaders)
  if ($RepoConfig.host -eq 'github') { return @(& gh pr diff $Pr -R "$($RepoConfig.owner)/$($RepoConfig.name)" 2>$null) }
  $diff = Invoke-Bitbucket -Headers $BitbucketHeaders -Path "repositories/$($RepoConfig.workspace)/$($RepoConfig.name)/pullrequests/$Pr/diff" -Raw
  return @($diff -split "`r?`n")
}
