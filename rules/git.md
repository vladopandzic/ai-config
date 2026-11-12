# Git guide

Read this before committing, creating a branch, pushing or opening a pull request.

## Commit mode

Before the first code change in a task, ask the user which mode to use, unless the user or the project's CLAUDE.md already chose one. The choice covers the current task only.

1. **Autonomous**: commit each logical step yourself and keep going.
2. **Step by step**: make one logical step, leave it uncommitted for review, commit after the user's OK, then continue with the next step.
3. **Prepared, reviewed one by one**: first do all the work as commits on a local helper branch `<branch>-prep`, which is never pushed. Then bring the commits to the working branch one at a time without committing them (`git cherry-pick -n <commit>`), so the user reviews exactly one commit's changes. After the user's OK, commit it with the prepared message (`git commit -C <commit>`) and bring the next one. If the user changed something during review and the next commit conflicts, resolve it and say so. Delete the helper branch at the end.
4. **No commits**: leave everything uncommitted; the user commits.

## Commits

- Each commit is one logical change that builds. Keep refactoring and formatting in separate commits from behavior changes.
- Never commit on `main`, `master`, `dev` or `develop`. Before the first commit there, ask the user what to name the new branch, and suggest a name that follows the project's convention.
- Match the commit message style of the repository: look at the user's last ~20 commits and use the same format, language and ticket key. If `%USERPROFILE%\.claude\clients.md` exists, also follow the commit style given there for this client.
- Write a one-line subject. Add a body only when the reason for the change is not obvious from the subject and the code.
- Never add "Co-Authored-By" lines or any AI attribution (Claude, Codex or similar) to commit messages.
- Do not commit build output, local settings or secrets (`bin/`, `obj/`, `.env`, local appsettings, `.claude/settings.local.json`).

## Branches

- Before starting work, check which branch you are on and say it. New work starts from the up-to-date remote base branch (fetch first), on a branch named after the ticket.
- Do not mix unrelated changes into the current branch.
- Follow the project's branch naming, for example `ABC-123-short-description`, `feature/short-description` or module branches.
- Never let a new feature branch track `origin/master` (or `origin/main`). After `git checkout -b NEW origin/master` (or any similar command), Git sets the new branch to track master — a future bare `git push` or `git pull` would hit master. Immediately run `git branch --unset-upstream <NEW>`, or use `git switch -c NEW --no-track origin/master` from the start. The branch should only get an upstream when it is first pushed with `git push -u origin NEW`, which points it at its own remote.

## Push

- Never push unless the user asks for that push.

## Dangerous operations

- Before a force push, a rebase of a pushed branch, `reset --hard`, deleting a branch, `git clean`, or discarding uncommitted changes, describe what will be lost and wait for the user's confirmation.

## Pull requests

- The description has: the ticket key or link; what changed and why; how it was tested; risks and breaking changes (API contract, migrations, configuration).
- Write it in the same language as the project's commit messages.
