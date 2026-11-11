# Links the AI rule files from this repo into the places where Claude Code and Codex read them.
#
# Run once on every machine after cloning (needs Windows Developer Mode for symlinks without admin):
#   git clone https://github.com/vladopandzic/ai-config.git $HOME\ai-config
#   & $HOME\ai-config\install.ps1
#
# Safe to run again: links that already point to this repo are left alone, and an existing
# regular file is renamed to <name>.backup-<timestamp> before the link replaces it.

$ErrorActionPreference = 'Stop'

$repositoryRoot = $PSScriptRoot
$homeDirectory = $env:USERPROFILE

function New-RuleFileLink
{
    param(
        [string] $LinkPath,
        [string] $RepositoryFilePath
    )

    $existingItem = Get-Item -LiteralPath $LinkPath -Force -ErrorAction SilentlyContinue
    $linkAlreadyPointsToRepository = $existingItem -and $existingItem.LinkType -eq 'SymbolicLink' -and $existingItem.Target -eq $RepositoryFilePath

    if ($linkAlreadyPointsToRepository)
    {
        Write-Host "ok       $LinkPath"
        return
    }

    if ($existingItem)
    {
        $backupPath = "$LinkPath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -LiteralPath $LinkPath -Destination $backupPath
        Write-Host "backup   $LinkPath -> $backupPath"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $LinkPath) | Out-Null
    New-Item -ItemType SymbolicLink -Path $LinkPath -Target $RepositoryFilePath | Out-Null
    Write-Host "linked   $LinkPath -> $RepositoryFilePath"
}

# Shared rules: Codex reads AGENTS.md directly, Claude reads CLAUDE.md, which imports AGENTS.md.
New-RuleFileLink -LinkPath "$homeDirectory\.codex\AGENTS.md" -RepositoryFilePath "$repositoryRoot\AGENTS.md"
New-RuleFileLink -LinkPath "$homeDirectory\.claude\CLAUDE.md" -RepositoryFilePath "$repositoryRoot\CLAUDE.md"

# Language guides: Claude loads files in ~/.claude/rules automatically for matching paths.
# Codex finds the same files through the index in AGENTS.md.
foreach ($guide in Get-ChildItem -Path "$repositoryRoot\rules" -Filter '*.md')
{
    New-RuleFileLink -LinkPath "$homeDirectory\.claude\rules\$($guide.Name)" -RepositoryFilePath $guide.FullName
}
