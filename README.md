# ai-config

My rules for AI coding agents (Claude Code and Codex), shared between my machines.

| File | Read by | Linked to |
|---|---|---|
| `AGENTS.md` | Codex directly, Claude through `CLAUDE.md` | `~/.codex/AGENTS.md` |
| `CLAUDE.md` | Claude only | `~/.claude/CLAUDE.md` |
| `rules/*.md` | Claude automatically by file path, Codex through the index in `AGENTS.md` | `~/.claude/rules/` |

Shared rules go in `AGENTS.md`. `CLAUDE.md` only imports it and holds Claude-only notes.

## New machine

1. Turn on Windows Developer Mode (Settings → System → For developers), so symlinks work without admin.
2. Clone into the home folder (the rule files reference `~/ai-config`):

   ```powershell
   git clone https://github.com/vladopandzic/ai-config.git $HOME\ai-config
   & $HOME\ai-config\install.ps1
   ```

## Never commit

Credentials and machine state stay out of this repo: `.credentials.json`, `.claude.json`, `auth.json`, `*.cred`, history and session files.
