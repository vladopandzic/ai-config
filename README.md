# ai-config

My rules for AI coding agents (Claude Code and Codex), shared between my machines.

| File | Read by | Connected through |
|---|---|---|
| `AGENTS.md` | Codex directly, Claude through `CLAUDE.md` | `%USERPROFILE%\.codex\AGENTS.md` |
| `CLAUDE.md` | Claude only | `%USERPROFILE%\.claude\CLAUDE.md` |
| `rules/*.md` | Claude automatically by file path, Codex through the index in `AGENTS.md` | `%USERPROFILE%\.claude\rules\ai-config-*.md` |
| `skills\<name>\` | Claude as skills (for example `/self-improve`) | `%USERPROFILE%\.claude\skills\<name>` |
| `AGENTS.local.md` (not in git) | Claude through the import in `CLAUDE.md`, Codex through the instruction in `AGENTS.md` | Created by `install.ps1` |

Shared rules go in `AGENTS.md`. `CLAUDE.md` only imports it and holds Claude-only notes.

## Personal preferences

`AGENTS.local.md` holds your own way of working: language and tone, the tools you use, how you want files handed to you. Everything that is about you rather than about the code goes there, so it stays out of the shared rules.

- It is in `.gitignore`, so it never leaves the machine and colleagues using this repo do not see it.
- `install.ps1` creates it from a short template if it is missing. An existing file is never touched.
- Where it conflicts with `AGENTS.md`, it wins.
- It is not synced between machines. Copy it by hand to a new machine.

## Skills

Folders in `skills\` are Claude Code skills. `install.ps1` links each one into `%USERPROFILE%\.claude\skills\` with a junction, so it works without Developer Mode.

### /self-improve

Turns your repeated corrections into rules, in the right file, one proposal at a time and only with your approval.

- `/self-improve`: looks at the current session. Run it after a bigger piece of work.
- `/self-improve history 30`: looks at your messages from all projects in the last 30 days. Run it about once a month.
- `/self-improve voice 30`: looks at your complaints about how Claude writes (unclear, too long, sounds like AI), each with the reply you reacted to, and proposes wording rules.

It needs Python for the history scan. Your decisions (written, skipped) go to `self-improve.local.md`, which git ignores, so a skipped rule is not proposed again unless it keeps coming back.

### /pr-review

Reviews a pull request on GitHub or Bitbucket from nine angles (bugs, architecture, tests, security, performance, conventions, ticket, unresolved comments, design questions), proves bugs with a test it actually runs, and drafts the comments. Nothing is posted until you say so.

Your repos go in `skills\pr-review\config.local.ps1` and notes about one repo in `skills\pr-review\repos\<repo>.md`; git ignores both. Setup is in `skills\pr-review\README.md`.

### /ef-migration

Adds, checks, removes and applies EF Core migrations in any .NET repo. It finds the context, project and migrations folder from the repo itself (documented `dotnet ef` commands first), reviews the new migration for data loss, warns when the base branch has a migration you do not, and touches only a local database, after you confirm.

- `/ef-migration add <name or what changed>`
- `/ef-migration check`: before a PR or after merging the base branch.
- `/ef-migration remove`, `/ef-migration update [migration]`, `/ef-migration script`

### /prepare-pr

Gets the current branch ready for a pull request: runs locally what the repo's CI runs (in a clean clone, with CI's .NET version), checks migrations and submodules, looks through the diff for leftovers and drafts the PR description. It never pushes or opens the PR on its own. `/prepare-pr quick` runs only the tests for the changed projects.

### /release

Prepares a release the way the repo already does it: reads the release docs, CI tag patterns and earlier tags, proposes the next version, lists what goes in and the migrations the release will run, and makes the release branch with the version bump locally. The branch and the annotated tag are pushed only after an explicit yes, because the tag usually deploys.

## Keeping clients out of the repo

This repo is meant to be shared, so a pre-commit hook runs `check-no-clients.ps1` on the lines you are about to commit and stops the commit if it finds an e-mail address, a personal Windows path, a token, or anything from your own denylist.

- Your denylist is `%USERPROFILE%\.claude\denylist.txt`: client names, colleagues, repo names, ticket keys, accounts, one case-insensitive regex per line. It never goes into git.
- `install.ps1` turns the hook on. Without a denylist only the general patterns run.
- `& .\check-no-clients.ps1 -All` checks every tracked file, not only what is staged.

## What install.ps1 does

It never deletes or replaces a file the user already has. Running it again only adds what is missing.

| Target | If it already exists | If it is missing |
|---|---|---|
| `%USERPROFILE%\.claude\CLAUDE.md` | Keeps the content, appends an import of this repo's `CLAUDE.md` (for example `@C:/Users/me/ai-config/CLAUDE.md`) | Creates it with that import line |
| `%USERPROFILE%\.codex\AGENTS.md` | Keeps the content, appends a "Shared rules" section pointing Codex to this repo's `AGENTS.md` (Codex has no imports) | Creates it with that section |
| `%USERPROFILE%\.claude\rules\ai-config-<guide>.md` | A copy made by `install.ps1` is refreshed; any other real file with that name is left untouched and reported as skipped | Links it to `rules/<guide>.md`, or copies it when symlinks are not allowed |
| `AGENTS.local.md` in this repo | Left untouched | Creates it from a template |

Before appending to an existing file it saves a copy as `<file>.backup-<timestamp>`. The user's own files in `%USERPROFILE%\.claude\rules\` keep working next to these guides.

### Where the repo lives

The repo can be cloned into any folder. Inside it every reference is relative (`@AGENTS.md`, `rules/csharp.md`), and `install.ps1` writes the repo's real path into `%USERPROFILE%\.claude\CLAUDE.md` and `%USERPROFILE%\.codex\AGENTS.md`. Keep the path free of spaces; `@` imports may not handle them.

After moving the repo, run `install.ps1` again from the new place. It reports the old lines as `outdated` and prints the new ones to paste in; it does not rewrite your files.

### Links or copies

Symlinks on Windows need Developer Mode (Settings → System → For developers) or an admin shell. With them, `%USERPROFILE%\.claude\rules\` holds links into this repo, so a `git pull` is enough to update the guides.

Without them, `install.ps1` copies the guides instead. A copy ends with an `ai-config` marker comment so the script can recognise it, and every run overwrites it with the current guide, so after a pull run `update.ps1`. Edit the guides in this repo, not the copies.

## Updating after a change on another machine

```powershell
& $HOME\ai-config\update.ps1
```

It runs `git pull` and then `install.ps1`, so guides added on the other machine are linked too.

## New machine

1. Optionally turn on Windows Developer Mode (Settings → System → For developers), so guides are linked instead of copied.
2. Clone into any folder; the examples use the home folder. The repo is private, so clone with the personal GitHub account:

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
| `%USERPROFILE%\.claude\clients.md` (my clients, trackers, commit styles) | `rules/git.md` | Not in this repo. Without it the commit style comes from the repository's git history only. |
| GitHub account `vladopandzic` | README "New machine" steps | Clone with your own access, or copy the files. |
| Windows Developer Mode | `install.ps1` (symlinks) | Guides are copied instead of linked; run `update.ps1` after every pull to refresh them. |

## Never commit

Credentials and machine state stay out of this repo: `.credentials.json`, `.claude.json`, `auth.json`, `*.cred`, history and session files. Personal preferences go in `AGENTS.local.md`, which git ignores.
