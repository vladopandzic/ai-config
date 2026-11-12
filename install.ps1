# Connects the AI rules in this repo to the places where Claude Code and Codex read them,
# without deleting or replacing anything the user already has.
#
# Run once on every machine after cloning this repo into any folder (see README.md):
#   & <repo folder>\install.ps1
#
# What it does (safe to run again; it only adds what is missing):
#   %USERPROFILE%\.claude\CLAUDE.md   existing file: keeps its content and appends one import line for this repo's CLAUDE.md.
#                                     missing file:  creates it with that import line.
#   %USERPROFILE%\.codex\AGENTS.md    existing file: keeps its content and appends a short section telling Codex
#                                     to read this repo's AGENTS.md.
#                                     missing file:  creates it with that section.
#                                     Both write this repo's real path; after moving the repo, run install.ps1 again.
#   %USERPROFILE%\.claude\rules\      links each guide as ai-config-<name>.md, so it never collides with the
#                                     user's own rule files. Without Windows Developer Mode (or an admin shell)
#                                     symlinks are not allowed, so the guide is copied instead and refreshed on every run.
#   %USERPROFILE%\.claude\skills\     links each skill folder (for example self-improve) with a junction,
#                                     which needs no Developer Mode. A folder with the same name is left untouched.
#   AGENTS.local.md                   missing file:  creates it from a template for personal preferences (not in git).
# Every existing file is copied to <name>.backup-<timestamp> before anything is appended to it.

param(
    [string] $HomeDirectory = $env:USERPROFILE
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = $PSScriptRoot
$repositoryRootForwardSlashes = $repositoryRoot.Replace('\', '/')
$RULES_MARKER = '<!-- ai-config: shared rules -->'
$GUIDE_LINK_PREFIX = 'ai-config-'
$GUIDE_COPY_MARKER = '<!-- ai-config: copy of a guide in this repo; install.ps1 overwrites it, edit the repo instead -->'

function Write-Status
{
    param(
        [string] $Status,
        [string] $Message
    )

    Write-Host ('{0,-9}{1}' -f $Status, $Message)
}

function Test-LinkPointsTo
{
    param(
        [System.IO.FileSystemInfo] $Item,
        [string] $TargetPath
    )

    return $Item -and $Item.LinkType -in 'SymbolicLink', 'Junction' -and $Item.Target -eq $TargetPath
}

function Backup-File
{
    param(
        [string] $FilePath
    )

    $backupPath = "$FilePath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item -LiteralPath $FilePath -Destination $backupPath
    Write-Status -Status 'backup' -Message "$FilePath -> $backupPath"
}

function Add-SharedRulesSection
{
    param(
        [string] $FilePath,
        [string] $SectionText
    )

    $existingContent = Get-Content -LiteralPath $FilePath -Raw
    $sectionAlreadyAdded = $existingContent -and $existingContent.Contains($RULES_MARKER)

    if ($sectionAlreadyAdded)
    {
        $sectionIsCurrent = ($existingContent -replace "`r`n", "`n").Contains(($SectionText -replace "`r`n", "`n"))

        if ($sectionIsCurrent)
        {
            Write-Status -Status 'ok' -Message $FilePath
            return
        }

        Write-Status -Status 'outdated' -Message "$FilePath has an older ai-config section (repo moved?); replace the lines after $RULES_MARKER by hand with:`n$SectionText"
        return
    }

    Backup-File -FilePath $FilePath
    Add-Content -LiteralPath $FilePath -Value "`n$RULES_MARKER`n$SectionText"
    Write-Status -Status 'appended' -Message $FilePath
}

function Get-GuideCopyContent
{
    param(
        [string] $GuidePath
    )

    return (Get-Content -LiteralPath $GuidePath -Raw) + "`n$GUIDE_COPY_MARKER`n"
}

function Test-IsGuideCopy
{
    param(
        [System.IO.FileSystemInfo] $Item
    )

    $isRegularFile = $Item -and -not $Item.LinkType -and -not $Item.PSIsContainer

    return $isRegularFile -and (Get-Content -LiteralPath $Item.FullName -Raw).Contains($GUIDE_COPY_MARKER)
}

function Update-GuideCopy
{
    param(
        [string] $CopyPath,
        [string] $GuidePath
    )

    $expectedContent = Get-GuideCopyContent -GuidePath $GuidePath
    $copyIsCurrent = (Get-Content -LiteralPath $CopyPath -Raw) -eq $expectedContent

    if ($copyIsCurrent)
    {
        Write-Status -Status 'ok' -Message $CopyPath
        return
    }

    Set-Content -LiteralPath $CopyPath -Value $expectedContent -NoNewline
    Write-Status -Status 'updated' -Message "$CopyPath <- $GuidePath"
}

function New-GuideFile
{
    param(
        [string] $LinkPath,
        [string] $GuidePath
    )

    New-Item -ItemType Directory -Force -Path (Split-Path $LinkPath) | Out-Null

    try
    {
        New-Item -ItemType SymbolicLink -Path $LinkPath -Target $GuidePath | Out-Null
        Write-Status -Status 'linked' -Message "$LinkPath -> $GuidePath"
    }
    catch
    {
        Set-Content -LiteralPath $LinkPath -Value (Get-GuideCopyContent -GuidePath $GuidePath) -NoNewline
        Write-Status -Status 'copied' -Message "$LinkPath <- $GuidePath (symlinks not allowed; turn on Developer Mode to link instead)"
    }
}

function Connect-ClaudeInstructions
{
    $claudeFilePath = "$HomeDirectory\.claude\CLAUDE.md"
    $repositoryClaudeFilePath = "$repositoryRoot\CLAUDE.md"
    $existingItem = Get-Item -LiteralPath $claudeFilePath -Force -ErrorAction SilentlyContinue

    if (Test-LinkPointsTo -Item $existingItem -TargetPath $repositoryClaudeFilePath)
    {
        Write-Status -Status 'ok' -Message $claudeFilePath
        return
    }

    $importLine = "@$repositoryRootForwardSlashes/CLAUDE.md"

    if (-not $existingItem)
    {
        New-Item -ItemType Directory -Force -Path (Split-Path $claudeFilePath) | Out-Null
        Set-Content -LiteralPath $claudeFilePath -Value "$RULES_MARKER`n$importLine"
        Write-Status -Status 'created' -Message $claudeFilePath
        return
    }

    Add-SharedRulesSection -FilePath $claudeFilePath -SectionText $importLine
}

function Connect-CodexInstructions
{
    $codexFilePath = "$HomeDirectory\.codex\AGENTS.md"
    $repositoryAgentsFilePath = "$repositoryRoot\AGENTS.md"
    $existingItem = Get-Item -LiteralPath $codexFilePath -Force -ErrorAction SilentlyContinue

    # Codex cannot import files, so its AGENTS.md gets a pointer to the shared rules.
    $pointerSection = @'
## Shared rules

Read and follow `{0}/AGENTS.md` before writing or reviewing code. It contains the shared coding rules and the index of language and topic guides.
'@ -f $repositoryRootForwardSlashes

    # Earlier versions linked this file to the repo's AGENTS.md, whose relative paths would then
    # resolve against %USERPROFILE%\.codex. Removing the link deletes no content.
    if (Test-LinkPointsTo -Item $existingItem -TargetPath $repositoryAgentsFilePath)
    {
        Remove-Item -LiteralPath $codexFilePath
        $existingItem = $null
    }

    if (-not $existingItem)
    {
        New-Item -ItemType Directory -Force -Path (Split-Path $codexFilePath) | Out-Null
        Set-Content -LiteralPath $codexFilePath -Value "$RULES_MARKER`n$pointerSection"
        Write-Status -Status 'created' -Message $codexFilePath
        return
    }

    Add-SharedRulesSection -FilePath $codexFilePath -SectionText $pointerSection
}

function Connect-ClaudeGuides
{
    $claudeRulesDirectory = "$HomeDirectory\.claude\rules"

    foreach ($guide in Get-ChildItem -Path "$repositoryRoot\rules" -Filter '*.md')
    {
        $linkPath = "$claudeRulesDirectory\$GUIDE_LINK_PREFIX$($guide.Name)"
        $existingItem = Get-Item -LiteralPath $linkPath -Force -ErrorAction SilentlyContinue

        if (Test-LinkPointsTo -Item $existingItem -TargetPath $guide.FullName)
        {
            Write-Status -Status 'ok' -Message $linkPath
            continue
        }

        if (Test-IsGuideCopy -Item $existingItem)
        {
            Update-GuideCopy -CopyPath $linkPath -GuidePath $guide.FullName
            continue
        }

        if ($existingItem)
        {
            Write-Status -Status 'skipped' -Message "$linkPath already exists and is not a link to this repo; left untouched"
            continue
        }

        New-GuideFile -LinkPath $linkPath -GuidePath $guide.FullName
    }

    Remove-UnprefixedGuideLinks -ClaudeRulesDirectory $claudeRulesDirectory
}

function Remove-UnprefixedGuideLinks
{
    # Earlier versions linked guides without the prefix. Those links point into this repo,
    # so removing them deletes no content; any real file with the same name is never touched.
    param(
        [string] $ClaudeRulesDirectory
    )

    foreach ($guide in Get-ChildItem -Path "$repositoryRoot\rules" -Filter '*.md')
    {
        $oldLinkPath = "$ClaudeRulesDirectory\$($guide.Name)"
        $oldItem = Get-Item -LiteralPath $oldLinkPath -Force -ErrorAction SilentlyContinue

        if (Test-LinkPointsTo -Item $oldItem -TargetPath $guide.FullName)
        {
            Remove-Item -LiteralPath $oldLinkPath
            Write-Status -Status 'renamed' -Message "$oldLinkPath -> $GUIDE_LINK_PREFIX$($guide.Name)"
        }
    }
}

function New-PersonalPreferencesFile
{
    $personalFilePath = "$repositoryRoot\AGENTS.local.md"

    if (Test-Path -LiteralPath $personalFilePath)
    {
        Write-Status -Status 'ok' -Message $personalFilePath
        return
    }

    $template = @'
# Personal preferences

<!-- Not in git. Your own way of working for Claude and Codex: language and tone, tools, how to hand you files. Shared coding rules belong in AGENTS.md. -->
'@
    Set-Content -LiteralPath $personalFilePath -Value $template
    Write-Status -Status 'created' -Message $personalFilePath
}

function Connect-ClaudeSkills
{
    $claudeSkillsDirectory = "$HomeDirectory\.claude\skills"

    foreach ($skill in Get-ChildItem -Path "$repositoryRoot\skills" -Directory)
    {
        $linkPath = "$claudeSkillsDirectory\$($skill.Name)"
        $existingItem = Get-Item -LiteralPath $linkPath -Force -ErrorAction SilentlyContinue

        if (Test-LinkPointsTo -Item $existingItem -TargetPath $skill.FullName)
        {
            Write-Status -Status 'ok' -Message $linkPath
            continue
        }

        if ($existingItem)
        {
            Write-Status -Status 'skipped' -Message "$linkPath already exists and is not a link to this repo; left untouched"
            continue
        }

        New-Item -ItemType Directory -Force -Path $claudeSkillsDirectory | Out-Null
        New-Item -ItemType Junction -Path $linkPath -Target $skill.FullName | Out-Null
        Write-Status -Status 'linked' -Message "$linkPath -> $($skill.FullName)"
    }
}

New-PersonalPreferencesFile
Connect-ClaudeInstructions
Connect-CodexInstructions
Connect-ClaudeGuides
Connect-ClaudeSkills
