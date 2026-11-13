---
name: ai-config-setup
description: Sets up this ai-config repo on a machine end to end. Runs install.ps1, then goes through everything check-setup.ps1 reports as missing and fixes it with the user one item at a time: tools, the gh login, the pr-review repo list and Bitbucket or Azure DevOps credentials, personal preferences and the denylist. Use when the user runs /ai-config-setup, has just cloned ai-config, or asks what is still missing for the skills to work.
---

# ai-config setup

Before `install.ps1` has run, this skill is not linked yet. On a fresh clone the user says: "Read `skills\ai-config-setup\SKILL.md` in this repo and follow it". After that, `/ai-config-setup` runs it again.

## 1. Install

- The repo root is two folders above this file's real location (`(Get-Item "$env:USERPROFILE\.claude\skills\ai-config-setup").Target` once it is linked).
- Run `install.ps1` from the repo root. It links the rules and skills, turns on the commit hook and ends with `check-setup.ps1`.
- Summarize what install changed (`created`, `linked`, `appended`, `copied`) in a few lines. A `skipped` or `outdated` line needs the user's attention: say what it means.

## 2. Fix what is missing

Go through the `missing` lines first, then the `note` lines, one at a time. For each, say in one sentence what it is for and offer the fix:

- **A tool** (git, PowerShell 7, gh, Python, .NET SDK): give the `winget install` command and run it only after a yes. Without winget (Windows Sandbox, LTSC and some company images have none), use each vendor's own installer: the zip from the PowerShell releases for pwsh, `dotnet-install.ps1` for .NET, the python.org installer for Python, the zip or MSI from the GitHub CLI releases for gh; also only after a yes. Prefer per-user installs that need no admin, and add their folders to the user's Path. If the user does not need what the tool is for (for example Python only for `/self-improve history`), skipping it is fine.
- **After installing**: this session still has the old Path, so before running `check-setup.ps1` again reload it: `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.
- **gh not logged in**: start `gh auth login --web --hostname github.com --git-protocol https` yourself in the background, read the one-time code from its output, and tell the user to open https://github.com/login/device, enter the code and approve. Do not hand the user a command to type: a `!` command in Claude Code runs in bash, not PowerShell, and long paths are hard to copy.
- **pr-review has no repo list**: do the `postavi` step of the `pr-review` skill.
- **Bitbucket variables or an Azure DevOps PAT variable**: as in `pr-review` `postavi`. The user sets tokens in their own terminal, never in the chat.
- **A repo without a local clone**: offer `git clone` into the folder the config names, or fix the path in the config.
- **Docker not running**: a note only; start Docker Desktop when integration tests are needed.
- **No denylist**: only matters for someone who commits to this repo. Offer to create `%USERPROFILE%\.claude\denylist.txt` with a header line and empty sections (clients, colleagues, repos, ticket keys), and let the user fill in the names.

## 3. Personal preferences

If `AGENTS.local.md` still holds only the template, ask three short questions and write the answers there:

- the language and tone for conversation;
- how files should be handed over (opened in a browser, an editor, or just the path);
- anything Claude keeps doing that they want to stop.

## 4. Check again

Run `check-setup.ps1` once more (with the reloaded Path) and report: what is `ok` now, what is still missing and why it was left (skipped by the user, needs something only they can do).

Then tell the user to close this Claude Code session and start a new one in any folder: skills linked during this session, such as `/pr-review` and `/pr-walkthrough`, appear only in new sessions, and new terminals also see the installed tools.

## Never

- Type, ask for or store a password, token or API key.
- Install software or clone a repo without a yes for that step.
- Change a file outside this repo and `%USERPROFILE%\.claude` without saying which file first.
