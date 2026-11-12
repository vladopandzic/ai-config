# Git guide

Read this before committing, creating a branch, pushing or opening a pull request.

## Commits

- Commit after each logical step while you work. Each commit is one logical change that builds. Keep refactoring and formatting in separate commits from behavior changes.
- Never commit on `main`, `master`, `dev` or `develop`. Before the first commit there, ask the user what to name the new branch, and suggest a name that follows the project's convention.
- Match the commit message style of the repository: look at the user's last ~20 commits and use the same format, language and ticket key. If `%USERPROFILE%\.claude\clients.md` exists, also follow the commit style given there for this client.
- Write a one-line subject. Add a body only when the reason for the change is not obvious from the subject and the code.
- Never add "Co-Authored-By" lines or any AI attribution (Claude, Codex or similar) to commit messages.
- Do not commit build output, local settings or secrets (`bin/`, `obj/`, `.env`, local appsettings, `.claude/settings.local.json`).

## Branches

- Follow the project's branch naming, for example `ABC-123-short-description`, `feature/short-description` or module branches.
- Never let a new feature branch track `origin/master` (or `origin/main`). After `git checkout -b NEW origin/master` (or any similar command), Git sets the new branch to track master — a future bare `git push` or `git pull` would hit master. Immediately run `git branch --unset-upstream <NEW>`, or use `git switch -c NEW --no-track origin/master` from the start. The branch should only get an upstream when it is first pushed with `git push -u origin NEW`, which points it at its own remote.

## Push

- Never push unless the user asks for that push.

## Dangerous operations

- Before a force push, a rebase of a pushed branch, `reset --hard`, deleting a branch, `git clean`, or discarding uncommitted changes, describe what will be lost and wait for the user's confirmation.

## Pull requests

- The description has: the ticket key or link; what changed and why; how it was tested; risks and breaking changes (API contract, migrations, configuration).
- Write it in the same language as the project's commit messages.
