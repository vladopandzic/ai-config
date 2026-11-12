# ai-config

My rules for AI coding agents (Claude Code and Codex), shared between my machines.

| File | Read by | Connected through |
|---|---|---|
| `AGENTS.md` | Codex directly, Claude through `CLAUDE.md` | `~/.codex/AGENTS.md` |
| `CLAUDE.md` | Claude only | `~/.claude/CLAUDE.md` |
| `rules/*.md` | Claude automatically by file path, Codex through the index in `AGENTS.md` | `~/.claude/rules/ai-config-*.md` |
| `AGENTS.local.md` (not in git) | Claude through the import in `CLAUDE.md`, Codex through the instruction in `AGENTS.md` | Created by `install.ps1` |

Shared rules go in `AGENTS.md`. `CLAUDE.md` only imports it and holds Claude-only notes.

## Personal preferences

`AGENTS.local.md` holds your own way of working: language and tone, the tools you use, how you want files handed to you. Everything that is about you rather than about the code goes there, so it stays out of the shared rules.

- It is in `.gitignore`, so it never leaves the machine and colleagues using this repo do not see it.
- `install.ps1` creates it from a short template if it is missing. An existing file is never touched.
- Where it conflicts with `AGENTS.md`, it wins.
- It is not synced between machines. Copy it by hand to a new machine.

## What install.ps1 does

It never deletes or replaces a file the user already has. Running it again only adds what is missing.

| Target | If it already exists | If it is missing |
|---|---|---|
| `~/.claude/CLAUDE.md` | Keeps the content, appends `@~/ai-config/CLAUDE.md` | Creates it with that import line |
| `~/.codex/AGENTS.md` | Keeps the content, appends a "Shared rules" section pointing Codex to `~/ai-config/AGENTS.md` (Codex has no imports) | Creates it with that section |
| `~/.claude/rules/ai-config-<guide>.md` | A copy made by `install.ps1` is refreshed; any other real file with that name is left untouched and reported as skipped | Links it to `rules/<guide>.md`, or copies it when symlinks are not allowed |
| `AGENTS.local.md` in this repo | Left untouched | Creates it from a template |

Before appending to an existing file it saves a copy as `<file>.backup-<timestamp>`. The user's own files in `~/.claude/rules/` keep working next to these guides.

### Links or copies

Symlinks on Windows need Developer Mode (Settings → System → For developers) or an admin shell. With them, `~/.claude/rules/` holds links into this repo, so a `git pull` is enough to update the guides.

Without them, `install.ps1` copies the guides instead. A copy ends with an `ai-config` marker comment so the script can recognise it, and every run overwrites it with the current guide, so after a pull run `update.ps1`. Edit the guides in this repo, not the copies.

## Updating after a change on another machine

```powershell
& $HOME\ai-config\update.ps1
```

It runs `git pull` and then `install.ps1`, so guides added on the other machine are linked too.

## New machine

1. Optionally turn on Windows Developer Mode (Settings → System → For developers), so guides are linked instead of copied.
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
| Windows Developer Mode | `install.ps1` (symlinks) | Guides are copied instead of linked; run `update.ps1` after every pull to refresh them. |

## Never commit

Credentials and machine state stay out of this repo: `.credentials.json`, `.claude.json`, `auth.json`, `*.cred`, history and session files. Personal preferences go in `AGENTS.local.md`, which git ignores.
