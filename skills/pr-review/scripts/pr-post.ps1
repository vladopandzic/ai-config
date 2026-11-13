<#
  pr-post.ps1 — post saved /pr-review draft comments to a GitHub, Bitbucket or Azure DevOps PR. SAFE BY DEFAULT.
  Without -Post it only DRY-RUNS (prints what would be posted). Nothing leaves the machine
  unless -Post is passed. Idempotent: comments already posted (posted=<id>) are skipped.

  GitHub inline comments need the line to exist in the PR diff; if it doesn't, the comment is posted
  as a general comment prefixed with "re: <path>:<line>" so nothing is lost.
  Bitbucket posting needs the write token BITBUCKET_<WORKSPACE>_TOKEN_WRITE (see pr-common.ps1).
  Azure DevOps posting uses the repo's tokenVariable PAT, which then needs Code (Read & write).

  Manifest = editable Markdown at <ReviewsDir>/<repo>-<pr>.md, one block per comment:
    ## PR-COMMENT 1 | inline | src/Shop.Api/Orders/OrderService.cs | 16 | posted=no
    <comment body, multi-line, until next "## PR-COMMENT" or EOF>
    ## PR-COMMENT 2 | reply | 123456789 | - | posted=no
  (general comment => path/line are "-"; reply => path is the id of the thread's first inline comment, line is "-";
   on Azure DevOps comment ids are <threadId>-<commentId> as the harvest gives them).
  On successful -Post, posted=no is rewritten to posted=<id>.

  Dedup: before showing/posting, the script fetches comments already on the PR and flags any draft
  that lands on the same file:line as an existing comment (±2 lines) — or, for general comments, one
  with strong word overlap. Inline duplicates are SKIPPED on -Post unless -Force is given; general
  duplicates are flagged in preview but not auto-skipped (fuzzy).

  Usage:
    pr-post.ps1 -Repo shop-api -Pr 42                       # DRY-RUN, all comments
    pr-post.ps1 -Repo shop-api -Pr 42 -Only 1,3             # DRY-RUN, only #1 #3
    pr-post.ps1 -Repo shop-api -Pr 42 -Only 1,3 -Post       # actually POST
    pr-post.ps1 -Repo shop-api -Pr 42 -Only 1 -Post -Force  # post even if dup
  -Repo may be left out when config.local.ps1 has exactly one repo.
#>
param(
  [string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [string]$File,                          # manifest path (default: <ReviewsDir>/<repo>-<pr>.md)
  [string]$Only,                          # comma list of comment numbers; empty = all unposted
  [switch]$Post,                          # WITHOUT this = dry run (safe). WITH = actually post.
  [switch]$Force                          # post even a comment flagged as a duplicate of an existing one
)
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'pr-common.ps1')
$configError = Import-ReviewConfig
if ($configError) { Write-Output "GREŠKA: $configError"; exit 0 }
$cfg = Resolve-RepoConfig $Repo
$problem = Get-ConfigError $cfg $Repo
if ($problem) { Write-Output "GREŠKA: $problem"; exit 0 }
$Repo = $cfg.name
$isGithub = $cfg.host -eq 'github'
$isAzure = $cfg.host -eq 'azure'
$slug = if ($isGithub) { "$($cfg.owner)/$Repo" } else { "$($cfg.workspace)/$Repo" }
$azureApi = if ($isAzure) { Get-AzureRepositoryApi $cfg } else { $null }
$readHeaders = switch ($cfg.host) {
  'github' { Use-GhAccount $cfg.ghAccount; $null }
  'azure' { Get-AzureHeaders $cfg.tokenVariable }
  default { Get-BitbucketHeaders $cfg.workspace }
}

if (-not $File) { $File = Join-Path $ReviewsDir "$Repo-$Pr.md" }
if (-not (Test-Path $File)) { Write-Output "GREŠKA: nema manifesta ($File). Prvo pokreni /pr-review $Repo $Pr."; exit 0 }

# --- parse manifest ---
$rx = '^##\s+PR-COMMENT\s+(\d+)\s*\|\s*(inline|general|reply)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|\s*posted=(\S+)\s*$'
$comments = @(); $cur = $null
foreach ($ln in (Get-Content -LiteralPath $File -Encoding utf8)) {
  if ($ln -match $rx) {
    if ($cur) { $comments += , $cur }
    $cur = [ordered]@{ n = [int]$Matches[1]; type = $Matches[2]; path = $Matches[3]; line = $Matches[4]; posted = $Matches[5]; body = @() }
  } elseif ($cur) { $cur.body += $ln }
}
if ($cur) { $comments += , $cur }
foreach ($c in $comments) { $c.text = (($c.body -join "`n").Trim()) }

$want = if ($Only) { @($Only -split ',' | ForEach-Object { [int]$_.Trim() }) } else { @($comments | ForEach-Object { $_.n }) }
$sel = @($comments | Where-Object { $want -contains $_.n })
if ($sel.Count -eq 0) { Write-Output "Nema komentara za odabir ($Only)."; exit 0 }

# --- DEDUP: fetch comments already on the PR and flag drafts that duplicate them (best-effort) ---
function New-ExistingComment($id, $replyTo, $author, $inline, $path, $line, $text) {
  [pscustomobject]@{ id = $id; replyTo = $replyTo; author = $author; inline = $inline
                     path = if ($path) { ($path -replace '\\', '/').ToLower() } else { $null }; line = $line; text = (($text -replace '\s+', ' ').Trim()) }
}
function Get-ExistingAzureComments {
  if (-not $readHeaders) { return $null }
  try { $threads = Get-AzureThreads $cfg $readHeaders $Pr } catch { return $null }
  return , @($threads | ForEach-Object {
    $thread = $_
    $path = ([string]$thread.threadContext.filePath).TrimStart('/')
    Get-AzureHumanComments $thread | ForEach-Object {
      $replyTo = if ($_.parentCommentId) { Get-AzureCommentId $thread $_.parentCommentId } else { $null }
      New-ExistingComment (Get-AzureCommentId $thread $_.id) $replyTo $_.author.displayName ([bool]$path) $path (Get-AzureThreadLine $thread) $_.content
    }
  })
}
function Get-ExistingPrComments {
  if ($isAzure) { return Get-ExistingAzureComments }
  if (-not $isGithub) {
    if (-not $readHeaders) { return $null }
    try {
      $values = Get-BitbucketPages $readHeaders "repositories/$slug/pullrequests/$Pr/comments?pagelen=100&fields=values.id,values.parent.id,values.content.raw,values.user.display_name,values.inline.path,values.inline.to,values.deleted,next"
    } catch { return $null }
    return , @($values | Where-Object { -not $_.deleted } | ForEach-Object {
      New-ExistingComment $_.id $_.parent.id $_.user.display_name ([bool]$_.inline) $_.inline.path $_.inline.to $_.content.raw })
  }
  $out = @()
  $inline = @(& gh api "repos/$slug/pulls/$Pr/comments" --paginate --jq '.[]' 2>$null)
  $inlineOk = $LASTEXITCODE -eq 0
  $out += @($inline | ForEach-Object { $_ | ConvertFrom-Json } | ForEach-Object {
    New-ExistingComment $_.id $_.in_reply_to_id $_.user.login $true $_.path $_.line $_.body })
  $general = @(& gh api "repos/$slug/issues/$Pr/comments" --paginate --jq '.[]' 2>$null)
  $out += @($general | ForEach-Object { $_ | ConvertFrom-Json } | ForEach-Object {
    New-ExistingComment $_.id $null $_.user.login $false $null $null $_.body })
  if ($out.Count -eq 0 -and -not $inlineOk) { return $null }
  return , @($out)
}
function Get-PrDiffLines {
  try { $diff = Get-PullRequestDiff $cfg $Pr $readHeaders } catch { return $null }
  if (-not $diff) { return $null }
  $map = @{}; $file = $null; $ln = 0
  foreach ($l in $diff) {
    if ($l -match '^\+\+\+ b/(.+)$') { $file = $Matches[1]; $map[$file] = [System.Collections.Generic.HashSet[int]]::new(); continue }
    if ($l -match '^@@ -\d+(,\d+)? \+(\d+)') { $ln = [int]$Matches[2]; continue }
    if (-not $file -or $l.StartsWith('-') -or $l.StartsWith('\') -or $l -match '^(diff |index )') { continue }
    if ($l.StartsWith('+') -or $l.StartsWith(' ')) { [void]$map[$file].Add($ln); $ln++ }
  }
  return $map
}
function Sig-Words($t) {
  @((([string]$t).ToLower() -replace '[^a-z0-9čćžšđ ]', ' ') -split '\s+' | Where-Object { $_.Length -ge 5 }) | Select-Object -Unique
}
function Find-DupComment($c, $existing) {
  if ($c.type -eq 'reply' -or -not $existing -or $existing.Count -eq 0) { return $null }
  if ($c.type -eq 'inline') {
    $p = ($c.path -replace '\\', '/').ToLower()
    $ln = 0; [void][int]::TryParse([string]$c.line, [ref]$ln)
    $cw = @(Sig-Words $c.text)
    foreach ($e in $existing) {
      if (-not $e.inline -or $e.path -ne $p -or -not $e.line) { continue }
      $delta = [Math]::Abs([int]$e.line - $ln)
      if ($delta -eq 0) { return $e }   # exact line = same thread
      if ($delta -le 2 -and $cw.Count) {  # near line: only a dup if the text also overlaps
        $ew = @(Sig-Words $e.text)
        if ($ew.Count -and (@($cw | Where-Object { $ew -contains $_ }).Count / [Math]::Min($cw.Count, $ew.Count)) -ge 0.4) { return $e }
      }
    }
    return $null
  }
  # general comment: no line to anchor on — flag only on strong word overlap (advisory, not auto-skipped)
  $cw = @(Sig-Words $c.text); if ($cw.Count -eq 0) { return $null }
  foreach ($e in $existing) {
    if ($e.inline) { continue }
    $ew = @(Sig-Words $e.text); if ($ew.Count -eq 0) { continue }
    $shared = @($cw | Where-Object { $ew -contains $_ }).Count
    if (($shared / [Math]::Min($cw.Count, $ew.Count)) -ge 0.5) { return $e }
  }
  return $null
}
$existing = Get-ExistingPrComments
$dupUnavailable = ($null -eq $existing)
foreach ($c in $sel) { $c.dup = if ($dupUnavailable) { $null } else { Find-DupComment $c $existing } }
$dupCount = @($sel | Where-Object { $_.dup }).Count

# --- DRY RUN (default): show exactly what would post ---
if (-not $Post) {
  Write-Output "PREVIEW — $Repo #$Pr  (ništa se ne šalje; dodaj -Post za slanje)"
  Write-Output ""
  $repoRoot = $cfg.localPath
  # read from the fetched pr-<n> ref when it exists (correct new-file lines); otherwise the local working tree
  $prRef = $null
  if ($repoRoot -and (Test-Path $repoRoot)) {
    & git -C $repoRoot rev-parse --verify --quiet "pr-$Pr" *> $null
    if ($LASTEXITCODE -eq 0) { $prRef = "pr-$Pr" }
  }
  $diffLines = if ($isGithub) { Get-PrDiffLines } else { $null }
  foreach ($c in $sel) {
    $flag = if ($c.posted -ne 'no') { "  [VEĆ OBJAVLJENO id=$($c.posted) - preskače se]" } else { "" }
    if ($c.type -eq 'inline') {
      Write-Output ("#{0} · inline · {1}:{2}{3}" -f $c.n, $c.path, $c.line, $flag)
      $diffKey = ($c.path -replace '\\', '/')
      $lineOutsideDiff = $isGithub -and $diffLines -and -not ($diffLines[$diffKey] -and $diffLines[$diffKey].Contains([int]$c.line))
      if ($lineOutsideDiff) {
        Write-Output "   ⚠️  linija nije u diffu: na objavi ide kao općeniti komentar s prefiksom re: <path>:<linija>"
      }
      # code snippet around the line, to show where the comment lands
      $pathFwd = ($c.path -replace '\\', '/')
      $srcLines = $null; $srcTag = ""
      if ($prRef) {
        $g = (& git -C $repoRoot show "${prRef}:$pathFwd" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $g) { $srcLines = @($g); $srcTag = "PR grana $prRef" }
      }
      if (-not $srcLines -and $repoRoot) {
        $full = Join-Path $repoRoot $c.path
        if (Test-Path $full) { $srcLines = @(Get-Content -LiteralPath $full -Encoding utf8); $srcTag = "working tree: $(Split-Path $repoRoot -Leaf)" }
      }
      if ($srcLines) {
        $ln = [int]$c.line
        $from = [Math]::Max(1, $ln - 3); $to = [Math]::Min($srcLines.Count, $ln + 2)
        Write-Output ("   ┌─ {0}  (linije {1}-{2}, izvor: {3})" -f (Split-Path $c.path -Leaf), $from, $to, $srcTag)
        for ($i = $from; $i -le $to; $i++) {
          $mark = if ($i -eq $ln) { "▶" } else { " " }
          Write-Output ("   │ {0} {1,5}| {2}" -f $mark, $i, $srcLines[$i - 1])
        }
        Write-Output "   └─"
      } else {
        Write-Output ("   (ne mogu pročitati kod za {0}:{1} — nema {2} ni fetchane grane)" -f $c.path, $c.line, $repoRoot)
      }
    } elseif ($c.type -eq 'reply') {
      Write-Output ("#{0} · ODGOVOR u niti {1}{2}" -f $c.n, $c.path, $flag)
      $parent = if ($existing) { @($existing | Where-Object { "$($_.id)" -eq $c.path })[0] }
      if (-not $parent) {
        Write-Output "   ⚠️  ne nalazim komentar s tim id-em: objava bi pala"
      } elseif ($isGithub -and $parent.replyTo) {
        Write-Output "   ⚠️  taj komentar je već odgovor: treba id prvog komentara niti ($($parent.replyTo))"
      } else {
        $q = $parent.text; if ($q.Length -gt 160) { $q = $q.Substring(0, 159) + [char]0x2026 }
        $where = if ($parent.path) { ", {0}:{1}" -f $parent.path, $parent.line } else { "" }
        Write-Output ("   odgovara na {0}{1}: {2}" -f $parent.author, $where, $q)
      }
    } else {
      Write-Output ("#{0} · OPĆENIT — ide u raspravu PR-a, NIJE vezan na liniju koda{1}" -f $c.n, $flag)
    }
    if ($c.dup) {
      $q = $c.dup.text; if ($q.Length -gt 160) { $q = $q.Substring(0, 159) + [char]0x2026 }
      $loc = if ($c.type -eq 'inline') { "na toj liniji" } else { "u raspravi" }
      Write-Output ("   ⚠️  MOŽDA DUPLIKAT — {0} već postoji komentar ({1}):" -f $loc, $c.dup.author)
      Write-Output ("       > {0}" -f $q)
      if ($c.type -eq 'inline') { Write-Output "       → preskače se na -Post (dodaj -Force da ipak objaviš)" }
      else { Write-Output "       → fuzzy pogodak; NE preskače se sam — provjeri i makni iz izbora ako je isto" }
    }
    Write-Output ""
    foreach ($bl in ($c.text -split "`n")) { Write-Output ("    {0}" -f $bl) }
    Write-Output ""
  }
  $skip = @($sel | Where-Object { $_.posted -eq 'no' -and $_.dup -and $_.type -eq 'inline' }).Count
  $todo = @($sel | Where-Object { $_.posted -eq 'no' -and -not ($_.dup -and $_.type -eq 'inline') }).Count
  if ($dupUnavailable) {
    $why = switch ($cfg.host) {
      'github' { 'gh ne može dohvatiti komentare (provjeri gh auth / SSO / račun)' }
      'azure' { "nema tokena u $($cfg.tokenVariable) ili Azure DevOps ne odgovara" }
      default { "nema read tokena $(Get-BitbucketVariablePrefix $cfg.workspace)_TOKEN ili Bitbucket ne odgovara" }
    }
    Write-Output "(⚠️ dedup preskočen — $why; preview je BEZ provjere duplikata)"
  } elseif ($dupCount -gt 0) {
    Write-Output "($dupCount označeno kao moguć duplikat; $skip inline se preskaču na -Post osim uz -Force)"
  }
  Write-Output "→ za slanje $todo komentar(a): dodaj -Post na isti poziv"
  exit 0
}

# --- REAL POST ---
if ($isGithub) {
  $ghHeadSha = (& gh api "repos/$slug/pulls/$Pr" --jq .head.sha 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $ghHeadSha) {
    Write-Output "GREŠKA: gh ne vidi $slug #$Pr. Provjeri: gh auth status, SSO autorizaciju org-a, i ghAccount u config.local.ps1."
    exit 0
  }
} elseif ($isAzure) {
  $writeHeaders = $readHeaders
  if (-not $writeHeaders) {
    Write-Output "GREŠKA: nema tokena u $($cfg.tokenVariable). PAT treba Code (Read & write), vidi README."
    exit 0
  }
  $lastIteration = (@((Invoke-Azure -Headers $writeHeaders -Uri "$azureApi/pullRequests/$Pr/iterations").value | ForEach-Object { [int]$_.id }) | Measure-Object -Maximum).Maximum
  $changeTrackingIdByPath = @{}
  foreach ($change in (Invoke-Azure -Headers $writeHeaders -Uri "$azureApi/pullRequests/$Pr/iterations/$lastIteration/changes?`$top=2000").changeEntries) {
    $changeTrackingIdByPath[([string]$change.item.path).TrimStart('/').ToLower()] = $change.changeTrackingId
  }
} else {
  $writeHeaders = Get-BitbucketHeaders $cfg.workspace -Write
  if (-not $writeHeaders) {
    $prefix = Get-BitbucketVariablePrefix $cfg.workspace
    Write-Output "GREŠKA: nema write tokena. Treba ${prefix}_EMAIL i ${prefix}_TOKEN_WRITE (scope write:pullrequest:bitbucket), vidi README."
    exit 0
  }
}

function Invoke-GithubPost($path, $body) {
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("prpost-{0}-{1}.json" -f $Repo, $Pr)
  ($body | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $tmp -Encoding utf8
  $resp = (& gh api --method POST $path --input $tmp 2>$null) | Out-String
  Remove-Item $tmp -Force
  $obj = $null; try { $obj = $resp | ConvertFrom-Json } catch {}
  return $obj
}

function Publish-GithubComment($c) {
  if ($c.type -eq 'reply') {
    $obj = Invoke-GithubPost "repos/$slug/pulls/$Pr/comments/$($c.path)/replies" @{ body = $c.text }
    if ($obj -and $obj.id) { return @{ id = "$($obj.id)" } }
    return @{ error = 'gh api POST reply nije vratio id — provjeri id niti i SSO/scope' }
  }
  if ($c.type -eq 'inline') {
    $obj = Invoke-GithubPost "repos/$slug/pulls/$Pr/comments" @{ body = $c.text; commit_id = $ghHeadSha; path = ($c.path -replace '\\', '/'); line = [int]$c.line; side = 'RIGHT' }
    if ($obj -and $obj.id) { return @{ id = "$($obj.id)" } }
    # line is not in the diff (GitHub requires it) -> keep the comment, post it as general with its location
    $obj2 = Invoke-GithubPost "repos/$slug/issues/$Pr/comments" @{ body = "**re: $($c.path):$($c.line)**`n`n$($c.text)" }
    if ($obj2 -and $obj2.id) { return @{ id = "$($obj2.id)"; note = 'linija nije u diffu → objavljen kao general s lokacijom' } }
    return @{ error = 'gh api POST (inline i fallback) nije vratio id — provjeri SSO/scope/da linija postoji' }
  }
  $obj = Invoke-GithubPost "repos/$slug/issues/$Pr/comments" @{ body = $c.text }
  if ($obj -and $obj.id) { return @{ id = "$($obj.id)" } }
  return @{ error = 'gh api POST nije vratio id — provjeri SSO/scope' }
}

function Publish-BitbucketComment($c) {
  $payload = @{ content = @{ raw = $c.text } }
  if ($c.type -eq 'inline') { $payload.inline = @{ path = ($c.path -replace '\\', '/'); to = [int]$c.line } }
  if ($c.type -eq 'reply') { $payload.parent = @{ id = [int]$c.path } }
  try {
    $resp = Invoke-Bitbucket -Headers $writeHeaders -Path "repositories/$slug/pullrequests/$Pr/comments" -Method Post -Body $payload
  } catch {
    return @{ error = "Bitbucket je odbio komentar: $($_.Exception.Message)" }
  }
  if ($resp.id) { return @{ id = "$($resp.id)" } }
  return @{ error = 'Bitbucket nije vratio id komentara' }
}

function Publish-AzureComment($c) {
  $comment = @{ parentCommentId = 0; content = $c.text; commentType = 1 }
  try {
    if ($c.type -eq 'reply') {
      $threadId, $parentCommentId = "$($c.path)" -split '-'
      $comment.parentCommentId = if ($parentCommentId) { [int]$parentCommentId } else { 1 }
      $resp = Invoke-Azure -Headers $writeHeaders -Uri "$azureApi/pullRequests/$Pr/threads/$threadId/comments" -Method Post -Body $comment
      return @{ id = "$threadId-$($resp.id)" }
    }
    $thread = @{ comments = @($comment); status = 1 }
    if ($c.type -eq 'inline') {
      $path = ($c.path -replace '\\', '/').TrimStart('/')
      $position = @{ line = [int]$c.line; offset = 1 }
      $thread.threadContext = @{ filePath = "/$path"; rightFileStart = $position; rightFileEnd = $position }
      $changeTrackingId = $changeTrackingIdByPath[$path.ToLower()]
      if ($changeTrackingId) {
        $thread.pullRequestThreadContext = @{ changeTrackingId = $changeTrackingId; iterationContext = @{ firstComparingIteration = 1; secondComparingIteration = $lastIteration } }
      }
    }
    $resp = Invoke-Azure -Headers $writeHeaders -Uri "$azureApi/pullRequests/$Pr/threads" -Method Post -Body $thread
    return @{ id = "$($resp.id)-$($resp.comments[0].id)" }
  } catch {
    return @{ error = "Azure DevOps je odbio komentar: $($_.Exception.Message)" }
  }
}

$posted = 0; $failed = 0
foreach ($c in $sel) {
  if ($c.posted -ne 'no') { Write-Output "#$($c.n) preskočen (već objavljen id=$($c.posted))"; continue }
  if ($c.dup -and $c.type -eq 'inline' -and -not $Force) {
    Write-Output "#$($c.n) ⏭  preskočen (duplikat — već postoji komentar na $($c.path):$($c.line) od $($c.dup.author); -Force da ipak objaviš)"
    continue
  }
  if ($c.type -eq 'reply' -and $c.path -notmatch '^\d+(-\d+)?$') {
    $failed++
    Write-Output "#$($c.n) ❌ NIJE objavljen: reply traži id komentara, a dobio je '$($c.path)'"
    continue
  }
  $r = switch ($cfg.host) {
    'github' { Publish-GithubComment $c }
    'azure' { Publish-AzureComment $c }
    default { Publish-BitbucketComment $c }
  }
  if ($r.id) {
    $c.posted = "$($r.id)"; $posted++
    $note = if ($r.note) { "  ($($r.note))" } else { "" }
    Write-Output "#$($c.n) ✅ objavljen (id=$($r.id))$note"
  } else {
    $failed++
    Write-Output "#$($c.n) ❌ NIJE objavljen: $($r.error)"
  }
}

# --- rewrite manifest with updated posted= flags (idempotency) ---
$out = @("<!-- pr-review $Repo#$Pr -->", "")
foreach ($c in $comments) {
  $out += ("## PR-COMMENT {0} | {1} | {2} | {3} | posted={4}" -f $c.n, $c.type, $c.path, $c.line, $c.posted)
  $out += ""
  $out += ($c.text -split "`n")
  $out += ""
}
$out | Set-Content -LiteralPath $File -Encoding utf8
Write-Output ""
Write-Output "Gotovo: $posted objavljeno, $failed neuspjelo. Manifest osvježen (posted= flagovi)."
