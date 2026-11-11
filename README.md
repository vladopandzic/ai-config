# ai-config

My rules for AI coding agents (Claude Code and Codex), shared between my machines.

| File | Read by | Connected through |
|---|---|---|
| `AGENTS.md` | Codex directly, Claude through `CLAUDE.md` | `~/.codex/AGENTS.md` |
| `CLAUDE.md` | Claude only | `~/.claude/CLAUDE.md` |
| `rules/*.md` | Claude automatically by file path, Codex through the index in `AGENTS.md` | `~/.claude/rules/ai-config-*.md` |

Shared rules go in `AGENTS.md`. `CLAUDE.md` only imports it and holds Claude-only notes.

## What install.ps1 does

It never deletes or replaces a file the user already has. Running it again only adds what is missing.

| Target | If it already exists | If it is missing |
|---|---|---|
| `~/.claude/CLAUDE.md` | Keeps the content, appends `@~/ai-config/CLAUDE.md` | Creates it with that import line |
| `~/.codex/AGENTS.md` | Keeps the content, appends a "Shared rules" section pointing Codex to `~/ai-config/AGENTS.md` (Codex has no imports) | Links it to this repo's `AGENTS.md` |
| `~/.claude/rules/ai-config-<guide>.md` | A real file with that name is left untouched and reported as skipped | Links it to `rules/<guide>.md` |

Before appending to an existing file it saves a copy as `<file>.backup-<timestamp>`. The user's own files in `~/.claude/rules/` keep working next to these guides.

## Updating after a change on another machine

```powershell
& $HOME\ai-config\update.ps1
```

It runs `git pull` and then `install.ps1`, so guides added on the other machine are linked too.

## New machine

1. Turn on Windows Developer Mode (Settings → System → For developers), so symlinks work without admin.
2. Clone into the home folder (the rule files reference `~/ai-config`). The repo is private, so clone with the personal GitHub account:

   ```powershell
   $env:GH_TOKEN = gh auth token --user vladopandzic
   gh repo clone vladopandzic/ai-config $HOME\ai-config
   Remove-Item Env:GH_TOKEN
   & $HOME\ai-config\install.ps1
   ```

3. If `gh` there is also logged in to a work account, make this repo always use the personal one:

   ```powershell
   git -C $HOME\ai-config config --local --add credential.helper ""
   git -C $HOME\ai-config config --local --add credential.helper '!f() { test "$1" = get && echo username=vladopandzic && echo password=$(gh auth token --user vladopandzic); }; f'
   ```

## Using these rules on someone else's machine

The rules work without any of my personal setup. A few things refer to it and are simply skipped or need adjusting:

| What | Where | What happens without it |
|---|---|---|
| `~/.claude/clients.md` (my clients, trackers, commit styles) | `rules/git.md` | Not in this repo. Without it the commit style comes from the repository's git history only. |
| GitHub account `vladopandzic` | README "New machine" steps | Clone with your own access, or copy the files. |
| The `~/ai-config` location | `AGENTS.md` index, `CLAUDE.md` import | Clone into `~/ai-config`, or change the paths in those two files. |
| Windows Developer Mode | `install.ps1` (symlinks) | Without it the links fail; turn it on or copy the files into `~/.claude` and `~/.codex` instead. |

## Never commit

Credentials and machine state stay out of this repo: `.credentials.json`, `.claude.json`, `auth.json`, `*.cred`, history and session files.
