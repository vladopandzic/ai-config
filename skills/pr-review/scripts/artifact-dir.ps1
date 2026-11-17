<#
  Folder for everything one ticket or pull request leaves behind (plan, review, contract check, app check, run log).

  <reviews dir>\<client>\<repo>\<key>\   when config.local.ps1 maps the repo to a client in $RepoClients
  <reviews dir>\<repo>\<key>\            otherwise

  <key> is a ticket key (ABC-123), PR-<number> (a bare number means a pull request) or WI-<number> (a work item written
  as #123). The folder is created, and <repo>\index.md gets one line per key.

  Command line:  pwsh -NoProfile -File artifact-dir.ps1 -Repo <name or path> -Key <ABC-123 | PR-42 | 42 | #123> [-Title "..."]
  In a script:   . <this file>; Get-ArtifactDir -Repo my-api -Key PR-42
#>
$ARTIFACT_CONFIG_PATH = Join-Path (Split-Path $PSScriptRoot -Parent) 'config.local.ps1'

function Get-ArtifactRoot {
  $reviewsDir = $null
  $repoClients = @{}
  if (Test-Path $ARTIFACT_CONFIG_PATH) {
    . $ARTIFACT_CONFIG_PATH
    if ($RepoClients) { $repoClients = $RepoClients }
  }
  if (-not $reviewsDir) { $reviewsDir = Join-Path $HOME 'pr-review' }
  [pscustomobject]@{ ReviewsDir = $reviewsDir; RepoClients = $repoClients }
}

function Resolve-ArtifactRepoName([string]$repo) {
  if (-not $repo) { $repo = (git rev-parse --show-toplevel 2>$null) }
  if (-not $repo) { throw 'artifact-dir: no repo given and the current folder is not a git repository' }
  if (Test-Path $repo -PathType Container) {
    $commonDir = git -C $repo rev-parse --path-format=absolute --git-common-dir 2>$null
    if ($commonDir) { return Split-Path (Split-Path $commonDir -Parent) -Leaf }
    return Split-Path $repo -Leaf
  }
  $repo
}

function Resolve-ArtifactKey([string]$key) {
  if (-not $key) { throw 'artifact-dir: no key (ticket key or PR number) given' }
  $trimmed = $key.Trim()
  if ($trimmed -match '^#(\d+)$') { return "WI-$($Matches[1])" }
  if ($trimmed -match '^\d+$') { return "PR-$trimmed" }
  if ($trimmed -match '^(?i)pr-(\d+)$') { return "PR-$($Matches[1])" }
  ($trimmed -replace '[\\/:*?"<>|]', '-')
}

function Get-ArtifactDir {
  param([string]$Repo, [string]$Key, [string]$Title)
  $root = Get-ArtifactRoot
  $repoName = Resolve-ArtifactRepoName $Repo
  $folderKey = Resolve-ArtifactKey $Key
  $client = $null
  foreach ($entry in $root.RepoClients.GetEnumerator()) {
    if ($entry.Key -ieq $repoName) { $client = $entry.Value }
  }
  $repoDir = if ($client) { Join-Path (Join-Path $root.ReviewsDir $client) $repoName } else { Join-Path $root.ReviewsDir $repoName }
  $dir = Join-Path $repoDir $folderKey
  New-Item -ItemType Directory -Force -Path $dir | Out-Null

  $index = Join-Path $repoDir 'index.md'
  if (-not (Test-Path $index)) { Set-Content -Path $index -Value "# $repoName`n" -Encoding utf8 }
  $link = "[$folderKey]($folderKey/)"
  $lines = @(Get-Content -Path $index -Encoding utf8)
  $listedAt = [Array]::FindIndex($lines, [Predicate[string]] { param($l) $l.Contains($link) })
  if ($listedAt -lt 0) {
    $line = "- $(Get-Date -Format 'yyyy-MM-dd') · $link"
    if ($Title) { $line += " · $Title" }
    Add-Content -Path $index -Value $line -Encoding utf8
  } elseif ($Title -and $lines[$listedAt].TrimEnd().EndsWith($link)) {
    $lines[$listedAt] = $lines[$listedAt].TrimEnd() + " · $Title"
    Set-Content -Path $index -Value $lines -Encoding utf8
  }
  $dir
}

# No param block: dot-sourcing must not overwrite the caller's $Repo, $Key or $Title.
if ($MyInvocation.InvocationName -ne '.') {
  $named = @{}
  for ($i = 0; $i -lt $args.Count - 1; $i += 2) { $named[([string]$args[$i]).TrimStart('-')] = $args[$i + 1] }
  Get-ArtifactDir -Repo $named['Repo'] -Key $named['Key'] -Title $named['Title']
}
