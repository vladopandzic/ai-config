<#
  The fixed steps of a second review round, so an unattended run needs no free shell commands.

  -Stage prepare: harvest, list the reviewer's threads in round.json and print the ones that still need a judgement.
  -Stage finish:  rebuild the walkthrough page with the round and write round-status.json.

  pwsh -NoProfile -File second_round.ps1 -Repo <repo> -Pr <number> -Stage prepare|finish
#>
param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [Parameter(Mandatory)][ValidateSet('prepare', 'finish')][string]$Stage
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$tools = $PSScriptRoot
$reviewScripts = Join-Path (Split-Path (Split-Path $tools -Parent) -Parent) 'pr-review\scripts'
. (Join-Path $reviewScripts 'artifact-dir.ps1')
$taskDir = Get-ArtifactDir -Repo $Repo -Key "PR-$Pr"
$data = Join-Path $taskDir "$Repo-$Pr.walkthrough"
$page = Join-Path $taskDir "$Repo-$Pr.walkthrough.html"
New-Item -ItemType Directory -Force (Join-Path $data 'parts') | Out-Null

function Read-Json($path) { Get-Content $path -Raw -Encoding utf8 | ConvertFrom-Json }
function Invoke-Python { python -I @args; if ($LASTEXITCODE) { throw "python $($args[0]) failed" } }
function Write-IfMissing($path, $text) { if (-not (Test-Path $path)) { Set-Content -Path $path -Value $text -Encoding utf8NoBOM -NoNewline } }

if ($Stage -eq 'prepare') {
  $scratch = Join-Path ([IO.Path]::GetTempPath()) "pr-walkthrough\$Repo-$Pr"
  New-Item -ItemType Directory -Force $scratch | Out-Null
  $harvestText = (pwsh -NoProfile -File (Join-Path $reviewScripts 'pr-harvest.ps1') -Repo $Repo -Pr $Pr -ScratchDir $scratch) -join "`n"
  $harvest = $harvestText | ConvertFrom-Json
  if ($harvest.error) { throw "harvest: $($harvest.error)" }
  Set-Content -Path (Join-Path $data 'harvest.json') -Value $harvestText -Encoding utf8NoBOM
  $reviewedHead = $harvest.previousReview.baseSha
  if (-not @($harvest.previousReview.myCommentIds).Count -or -not $reviewedHead) { throw 'no earlier review by the user on this PR, nothing for a second round' }
  $head = git -C $harvest.localPath rev-parse "pr-$Pr"
  Invoke-Python (Join-Path $tools 'review_round.py') (Join-Path $data 'harvest.json') $harvest.localPath $reviewedHead $head (Join-Path $data 'round.json')
  $round = Read-Json (Join-Path $data 'round.json')
  $todo = @($round.threads | Where-Object { -not $_.outcome })
  Write-Output "data=$data"
  Write-Output "repo=$($harvest.localPath) head=$head reviewed=$reviewedHead to judge=$($todo.Count) of $(@($round.threads).Count)"
  $todo | ForEach-Object { Write-Output ("  {0}  {1}:{2}" -f $_.id, $_.path, $_.headLine) }
  return
}

$harvest = Read-Json (Join-Path $data 'harvest.json')
$repoPath = $harvest.localPath
$head = git -C $repoPath rev-parse "pr-$Pr"
$base = git -C $repoPath merge-base "origin/$($harvest.dest)" "pr-$Pr"
$meta = if (Test-Path (Join-Path $data 'meta.json')) { Read-Json (Join-Path $data 'meta.json') } else { $null }

$parts = Join-Path $data 'parts'
Write-IfMissing (Join-Path $parts 'title.txt') "PR walkthrough: $($harvest.title)"
Write-IfMissing (Join-Path $parts 'header.html') ("<header class=`"pr-head`">`n  <h1>" + [Net.WebUtility]::HtmlEncode($harvest.title) + "</h1>`n</header>`n")
Write-IfMissing (Join-Path $parts 'footer.html') ''
Write-IfMissing (Join-Path $data 'lanes.json') '[]'
Write-IfMissing (Join-Path $data 'topics-human.json') '{"summary": {}, "flags": {}, "items": [], "highlights": {}}'
Write-IfMissing (Join-Path $data 'code-spec.json') (@{ repo = $repoPath -replace '\\', '/'; base = $base; head = $head; panels = @{} } | ConvertTo-Json)

if ($meta -and $meta.head -and $meta.head -ne $head) {
  Invoke-Python (Join-Path $tools 'delta.py') $repoPath $meta.head $head $data
}
$D = $data
Invoke-Python "$tools\code_panels.py" "$D\code-spec.json" "$D\code-panels.json"
Invoke-Python "$tools\make_page.py" "$tools\reference-template.html" "$D\parts" "$D\page-template.html"
Invoke-Python "$tools\pr_topics.py" $repoPath $base $head "$D\topics.json"
Invoke-Python "$tools\pr_meta.py" $repoPath auto $Pr $base $head "$D\meta.json" "$D\code-panels.json" "$D\topics.json"
Invoke-Python "$tools\pr_sources.py" $repoPath $base $head "$D\code-panels.json" "$D\sources.json"
Invoke-Python "$tools\pr_status.py" $repoPath $base $head "$D\harvest.json" "$D\prstatus.json"
Invoke-Python "$tools\pr_discussion.py" "$D\harvest.json" "$D\discussion.json"
$findings = Join-Path $taskDir "$Repo-$Pr.findings.json"
if (Test-Path $findings) { Copy-Item $findings "$D\findings.json" -Force }

$inputs = @("CODE=$D\code-panels.json", "SOURCES=$D\sources.json", "PRINFO=$D\prstatus.json", "TOPICS=$D\topics.json", "HUMAN=$D\topics-human.json",
  "LANES=$D\lanes.json", "META=$D\meta.json", "DISCUSSION=$D\discussion.json", "ROUND=$D\round.json")
$tone = Join-Path $reviewScripts '..\references\ton-komentara.md'
if (Test-Path $tone) { $inputs += "TONE=$((Resolve-Path $tone).Path)" }
foreach ($optional in 'OUTLINE=outline.json', 'ZOOM=zoom.json', 'FLOW=flow.json', 'DB=db.json', 'DELTA=delta.json', 'FINDINGS=findings.json') {
  $name, $file = $optional -split '=', 2
  if (Test-Path "$D\$file") { $inputs += "$name=$D\$file" }
}
Invoke-Python "$tools\build_page.py" "$D\page-template.html" $page @inputs
Invoke-Python "$tools\round_status.py" "$D\round.json" "$D\harvest.json" $page "$D\round-status.json"
