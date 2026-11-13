<#
  pr-harvest.ps1 — one-shot PR context harvester for /pr-review, GitHub (gh CLI) and Bitbucket (API token).
  Returns a single JSON manifest; saves the (possibly huge) diff to a file and returns its path.
  Repos, hosts and local clones come from config.local.ps1 (see config.example.ps1).

  Usage:
    pr-harvest.ps1 -List                     # open PRs of every configured repo
    pr-harvest.ps1 -List -Pretty             # same, as a ready-to-show Markdown table
    pr-harvest.ps1 -Repo shop-api -List
    pr-harvest.ps1 -Repo shop-api -Pr 42 -ScratchDir <dir>
  -Repo may be left out when config.local.ps1 has exactly one repo.

  Output JSON:
    list mode  -> { groups:[{ repo, host, prs:[{id,title,author,source,dest,comments,updated,approvers}] }] }
    single     -> { repo, host, pr, url, title, description, author, source, dest, state, headSha,
                    approvals:[{name,approved}], ci:[{state,name}], ticketKey,
                    comments:[{id,replyTo,author,created,inline,path,line,text}],
                    fetchSpec, diffPath, diffLines, previousReview, me, localPath, reviewsDir, notesPath }
#>
param(
  [string]$Repo,
  [int]$Pr,
  [switch]$List,
  [switch]$Pretty,
  [string]$ScratchDir = [IO.Path]::GetTempPath()
)
$ErrorActionPreference = 'Stop'
function Out-Json($o) { $o | ConvertTo-Json -Depth 8 -Compress }

. (Join-Path $PSScriptRoot 'pr-common.ps1')
$configError = Import-ReviewConfig
if ($configError) { Out-Json @{ error = $configError }; exit 0 }

function Get-PrUrl($repoConfig, $id) {
  if ($repoConfig.host -eq 'github') { return "https://github.com/$($repoConfig.owner)/$($repoConfig.name)/pull/$id" }
  return "https://bitbucket.org/$($repoConfig.workspace)/$($repoConfig.name)/pull-requests/$id"
}

function Write-PrGroup($repoConfig, $prs, $me) {
  $open = @($prs)
  Write-Output ('### {0} ({1})' -f $repoConfig.name, $open.Count)
  Write-Output ''
  if ($open.Count -eq 0) { Write-Output 'Nema otvorenih PR-ova.'; Write-Output ''; return }
  Write-Output '| PR | Naslov | Grana | Autor | Komentari | Dana | Approve |'
  Write-Output '|---|---|---|---|--:|--:|---|'
  foreach ($p in $open) {
    $title = ([string]$p.title) -replace '\|', '/'
    if ($title.Length -gt 36) { $title = $title.Substring(0, 35) + [char]0x2026 }
    $branch = ([string]$p.source) -replace '\|', '/'
    if ($branch.Length -gt 24) { $branch = $branch.Substring(0, 23) + [char]0x2026 }
    $age = ''
    if ($p.updated) { try { $age = [string][int]((Get-Date) - [datetime]$p.updated).TotalDays } catch { $age = '' } }
    $approverIds = @($p.approverIds)
    $approvedByMe = $me.id -and ($approverIds -contains $me.id)
    $approvals = if ($approvedByMe) { '{0} (i ti)' -f $approverIds.Count } elseif ($approverIds.Count -eq 0) { '-' } else { [string]$approverIds.Count }
    Write-Output ('| [{0}]({1}) | {2} | `{3}` | {4} | {5} | {6} | {7} |' -f $p.id, (Get-PrUrl $repoConfig $p.id), $title, $branch, $p.author, [int]$p.comments, $age, $approvals)
  }
  Write-Output ''
}

function Get-GithubPrs($repoConfig) {
  $slug = "$($repoConfig.owner)/$($repoConfig.name)"
  $list = gh pr list -R $slug --state open --json number,title,author,headRefName,baseRefName,comments,updatedAt,latestReviews --limit 50 | ConvertFrom-Json
  return @($list | ForEach-Object {
    $inlineCount = [int](gh api "repos/$slug/pulls/$($_.number)" --jq .review_comments)
    @{ id = $_.number; title = $_.title; author = $_.author.login; source = $_.headRefName; dest = $_.baseRefName
       comments = @($_.comments).Count + $inlineCount; updated = $_.updatedAt
       approverIds = @($_.latestReviews | Where-Object { $_.state -eq 'APPROVED' } | ForEach-Object { $_.author.login }) }
  })
}

function Get-BitbucketPrs($repoConfig, $headers) {
  $fields = 'values.id,values.title,values.author.display_name,values.source.branch.name,values.destination.branch.name,values.comment_count,values.updated_on,values.participants.approved,values.participants.user.account_id,next'
  $values = Get-BitbucketPages $headers "repositories/$($repoConfig.workspace)/$($repoConfig.name)/pullrequests?state=OPEN&pagelen=50&fields=$fields"
  return @($values | ForEach-Object {
    @{ id = $_.id; title = $_.title; author = $_.author.display_name; source = $_.source.branch.name; dest = $_.destination.branch.name
       comments = $_.comment_count; updated = [string]$_.updated_on
       approverIds = @($_.participants | Where-Object { $_.approved } | ForEach-Object { $_.user.account_id }) }
  })
}

function Get-Me($repoConfig, $headers) {
  if ($repoConfig.host -eq 'github') {
    $login = gh api user --jq .login 2>$null
    return @{ name = $login; id = $login }
  }
  try {
    $user = Invoke-Bitbucket -Headers $headers -Path 'user'
    return @{ name = $user.display_name; id = $user.account_id }
  } catch {
    return @{ name = $null; id = $repoConfig.bitbucketAccountId }
  }
}

function Get-RepoAccess($repoConfig) {
  if ($repoConfig.host -eq 'github') { Use-GhAccount $repoConfig.ghAccount; return @{ headers = $null; error = $null } }
  $headers = Get-BitbucketHeaders $repoConfig.workspace
  if ($headers) { return @{ headers = $headers; error = $null } }
  $prefix = Get-BitbucketVariablePrefix $repoConfig.workspace
  return @{ headers = $null; error = "nema ${prefix}_EMAIL / ${prefix}_TOKEN u environment varijablama (vidi README)" }
}

if ($List) {
  $repoNames = if ($Repo) { @($Repo) } else { @($ReviewRepos.Keys | Sort-Object) }
  $groups = @()
  foreach ($name in $repoNames) {
    $repoConfig = Resolve-RepoConfig $name
    $problem = Get-ConfigError $repoConfig $name
    if (-not $problem) {
      $access = Get-RepoAccess $repoConfig
      $problem = $access.error
    }
    if ($problem) { $groups += @{ repo = $name; error = $problem; prs = @() }; continue }
    $prs = if ($repoConfig.host -eq 'github') { Get-GithubPrs $repoConfig } else { Get-BitbucketPrs $repoConfig $access.headers }
    $me = Get-Me $repoConfig $access.headers
    $groups += @{ repo = $name; host = $repoConfig.host; config = $repoConfig; me = $me; prs = @($prs) }
  }
  if ($Pretty) {
    foreach ($group in $groups) {
      if ($group.error) { Write-Output ('### {0}' -f $group.repo); Write-Output ''; Write-Output "Greška: $($group.error)"; Write-Output ''; continue }
      Write-PrGroup $group.config $group.prs $group.me
    }
    Write-Output '→ za review: `/pr-review <repo> <broj>`'
    exit 0
  }
  Out-Json @{ groups = @($groups | ForEach-Object { @{ repo = $_.repo; host = $_.host; error = $_.error; prs = $_.prs } }) }
  exit 0
}

if (-not $Pr) { Out-Json @{ error = 'treba -List ili -Pr <broj>' }; exit 0 }

$cfg = Resolve-RepoConfig $Repo
$problem = Get-ConfigError $cfg $Repo
if ($problem) { Out-Json @{ error = $problem }; exit 0 }
if (-not $cfg.localPath -or -not (Test-Path (Join-Path $cfg.localPath '.git'))) {
  Out-Json @{ error = "localPath za '$($cfg.name)' u config.local.ps1 je prazan ili nije git klon: '$($cfg.localPath)'" }; exit 0
}
$access = Get-RepoAccess $cfg
if ($access.error) { Out-Json @{ error = $access.error }; exit 0 }
$Repo = $cfg.name

function Get-NotesHead($repo, $pr) {
  $notes = Join-Path $ReviewsDir "$repo-$pr.objasnjenje.md"
  if (-not (Test-Path $notes)) { return $null }
  $match = Select-String -Path $notes -Pattern 'Reviewano @ ([0-9a-f]{7,40})' | Select-Object -First 1
  if ($match) { return $match.Matches[0].Groups[1].Value }
  return $null
}

function New-PreviousReview($myLastAt, $baseSha, $baseSource, $headSha, $fetchSpec, $destBranch, $myCommentIds) {
  $result = [ordered]@{ at = $myLastAt; baseSha = $baseSha; baseSource = $baseSource; headSha = $headSha; myCommentIds = @($myCommentIds)
                        deltaAvailable = $false; deltaReason = $null; deltaDiffPath = $null; deltaDiffLines = 0; changedFiles = @(); commitsSince = @() }
  if (-not $myLastAt -and -not $baseSha) { $result.deltaReason = 'first review (no earlier comments/approval by you)'; return $result }
  if (-not $baseSha) { $result.deltaReason = 'could not resolve the head you reviewed'; return $result }
  $repoPath = $cfg.localPath
  git -C $repoPath fetch origin $fetchSpec $destBranch --quiet 2>$null | Out-Null
  git -C $repoPath cat-file -e "$baseSha^{commit}" 2>$null
  if ($LASTEXITCODE -ne 0) { git -C $repoPath fetch origin $baseSha --quiet 2>$null | Out-Null; git -C $repoPath cat-file -e "$baseSha^{commit}" 2>$null }
  if ($LASTEXITCODE -ne 0) { $result.deltaReason = "reviewed head $baseSha is no longer fetchable (force-push + gc?)"; return $result }

  # Only files this PR actually changes vs its target branch — merges of the target into the PR branch are noise, not the author's work.
  $dest = "origin/$destBranch"
  $prFiles = @(git -C $repoPath diff --name-only (git -C $repoPath merge-base $dest $headSha) $headSha)
  $previousPrFiles = @(git -C $repoPath diff --name-only (git -C $repoPath merge-base $dest $baseSha) $baseSha 2>$null)
  $reviewFiles = @($prFiles + $previousPrFiles | Sort-Object -Unique)
  $deltaPath = Join-Path $ScratchDir "pr-$Repo-$Pr.delta.diff"
  if ($reviewFiles.Count) { git -C $repoPath diff $baseSha $headSha -- $reviewFiles | Out-File $deltaPath -Encoding utf8 } else { '' | Out-File $deltaPath -Encoding utf8 }
  $result.deltaAvailable = $true
  $result.deltaDiffPath = $deltaPath
  $result.deltaDiffLines = (Get-Content $deltaPath | Measure-Object -Line).Lines
  $result.changedFiles = @(git -C $repoPath diff --name-only $baseSha $headSha -- $reviewFiles)
  $result.commitsSince = @(git -C $repoPath log --no-merges --format='%h %s' "$baseSha..$headSha" "^$dest" 2>$null)
  return $result
}

function Get-GithubPullRequest {
  $slug = "$($cfg.owner)/$Repo"
  $view = gh pr view $Pr -R $slug --json title,body,author,headRefName,headRefOid,baseRefName,state,reviews,statusCheckRollup,comments | ConvertFrom-Json
  $inline = @(gh api "repos/$slug/pulls/$Pr/comments" --paginate --jq '.[]' | ForEach-Object { $_ | ConvertFrom-Json })
  $me = (Get-Me $cfg $null).name
  $myReviews = @(gh api "repos/$slug/pulls/$Pr/reviews" --paginate --jq '.[]' 2>$null | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.user.login -eq $me -and $_.submitted_at })
  $lastReview = $myReviews | Sort-Object { [datetime]$_.submitted_at } -Descending | Select-Object -First 1
  $comments = @($view.comments | ForEach-Object { @{ id = $null; replyTo = $null; author = $_.author.login; created = $_.createdAt; inline = $false; path = $null; line = $null; text = ($_.body -replace '\s+', ' ') } })
  $comments += @($inline | ForEach-Object { @{ id = $_.id; replyTo = $_.in_reply_to_id; author = $_.user.login; created = $_.created_at; inline = $true; path = $_.path; line = $(if ($_.line) { $_.line } else { $_.original_line }); outdated = -not $_.line; text = ($_.body -replace '\s+', ' ') } })
  return @{
    title = $view.title; description = $view.body; author = $view.author.login; source = $view.headRefName; dest = $view.baseRefName
    state = $view.state; headSha = $view.headRefOid; me = $me
    approvals = @($view.reviews | ForEach-Object { @{ name = $_.author.login; approved = ($_.state -eq 'APPROVED') } })
    ci = @($view.statusCheckRollup | ForEach-Object { @{ state = $_.conclusion; name = $_.name } })
    comments = $comments
    fetchSpec = "+pull/$Pr/head:pr-$Pr"
    myLastAt = if ($lastReview) { $lastReview.submitted_at } else { $null }
    reviewedSha = if ($lastReview) { $lastReview.commit_id } else { $null }
    myActivityIds = @($myReviews | ForEach-Object { $_.id })
  }
}

function Get-BitbucketPullRequest($headers) {
  $base = "repositories/$($cfg.workspace)/$Repo/pullrequests/$Pr"
  $pullRequest = Invoke-Bitbucket -Headers $headers -Path "$base`?fields=title,description,state,author.display_name,source.branch.name,source.commit.hash,destination.branch.name,participants.approved,participants.role,participants.participated_on,participants.user.display_name,participants.user.account_id"
  $statuses = Get-BitbucketPages $headers "$base/statuses?pagelen=50&fields=values.state,values.name,next"
  $rawComments = Get-BitbucketPages $headers "$base/comments?pagelen=100&fields=values.id,values.parent.id,values.created_on,values.content.raw,values.user.display_name,values.user.account_id,values.inline.path,values.inline.to,values.deleted,next"
  $me = Get-Me $cfg $headers
  $liveComments = @($rawComments | Where-Object { -not $_.deleted })
  $myComments = @($liveComments | Where-Object { $me.id -and $_.user.account_id -eq $me.id })
  $myParticipant = @($pullRequest.participants | Where-Object { $me.id -and $_.user.account_id -eq $me.id })
  if (-not $me.name) { $me.name = @(@($myParticipant | ForEach-Object { $_.user.display_name }) + @($myComments | ForEach-Object { $_.user.display_name }))[0] }
  $myParticipation = @($myParticipant | Where-Object { $_.participated_on } | ForEach-Object { [string]$_.participated_on })
  $myLastAt = @(@($myComments | ForEach-Object { [string]$_.created_on }) + $myParticipation | Sort-Object { [datetime]$_ } -Descending)[0]
  return @{
    title = $pullRequest.title; description = $pullRequest.description; author = $pullRequest.author.display_name; source = $pullRequest.source.branch.name; dest = $pullRequest.destination.branch.name
    state = $pullRequest.state; headSha = $pullRequest.source.commit.hash; me = $me.name
    approvals = @($pullRequest.participants | Where-Object { $_.role -eq 'REVIEWER' -or $_.approved } | ForEach-Object { @{ name = $_.user.display_name; approved = [bool]$_.approved } })
    ci = @($statuses | ForEach-Object { @{ state = $_.state; name = $_.name } })
    comments = @($liveComments | ForEach-Object { @{ id = $_.id; replyTo = $_.parent.id; author = $_.user.display_name; created = [string]$_.created_on; inline = [bool]$_.inline; path = $_.inline.path; line = $_.inline.to; text = ($_.content.raw -replace '\s+', ' ') } })
    fetchSpec = "+refs/heads/$($pullRequest.source.branch.name):refs/heads/pr-$Pr"
    myLastAt = $myLastAt
    reviewedSha = $null
    myActivityIds = @($myComments | ForEach-Object { $_.id })
  }
}

$pull = if ($cfg.host -eq 'github') { Get-GithubPullRequest } else { Get-BitbucketPullRequest $access.headers }
$diffPath = Join-Path $ScratchDir "pr-$Repo-$Pr.diff"
Get-PullRequestDiff $cfg $Pr $access.headers | Out-File $diffPath -Encoding utf8
$key = $null; if ("$($pull.title) $($pull.source)" -match $cfg.ticketRegex) { $key = $Matches[0] }

$baseSha = Get-NotesHead $Repo $Pr; $baseSource = 'notes'
if (-not $baseSha -and $pull.reviewedSha) { $baseSha = $pull.reviewedSha; $baseSource = 'github-review' }
$previousReview = New-PreviousReview $pull.myLastAt $baseSha $baseSource $pull.headSha $pull.fetchSpec $pull.dest $pull.myActivityIds

Out-Json @{
  previousReview = $previousReview
  repo = $Repo; host = $cfg.host; pr = $Pr; url = (Get-PrUrl $cfg $Pr)
  title = $pull.title; description = $pull.description; author = $pull.author
  source = $pull.source; dest = $pull.dest; state = $pull.state; headSha = $pull.headSha
  approvals = $pull.approvals; ci = $pull.ci; ticketKey = $key; comments = $pull.comments
  fetchSpec = $pull.fetchSpec
  diffPath = $diffPath; diffLines = (Get-Content $diffPath | Measure-Object -Line).Lines
  me = $pull.me; localPath = $cfg.localPath; reviewsDir = $ReviewsDir
  notesPath = if (Test-Path $cfg.notesPath) { $cfg.notesPath } else { $null }
}
