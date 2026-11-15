---
name: update-docs
description: Checks a repo's instructions for agents and developers (CLAUDE.md, AGENTS.md, repo skills, README build/run sections) against the repo as it really is, and fixes what is wrong, stale or missing. Every claim is checked against the code, config or a command before it stays. "/update-docs" audits the whole repo; "/update-docs branch" checks only what the current branch's changes made outdated, as a step before a pull request. Use when the user runs /update-docs, asks to update or check CLAUDE.md or the docs, or a finish-the-branch flow needs the docs to match the change.
argument-hint: "[branch]"
---

# Update docs

Docs that agents read are only useful while they are true. This skill finds the sentences that are no longer true and the things nobody wrote down yet.

## 1. Scope

- **`/update-docs`**: every agent and build doc in the repo: `CLAUDE.md` and `AGENTS.md` at any level, `.claude/skills/*/SKILL.md`, `.claude/rules`, and the build, test and run sections of `README` and `docs/`.
- **`/update-docs branch`**: the diff of the current branch against its base (`git diff origin/<base>...HEAD`). Only docs that describe something the diff touched: a renamed project, command, setting, environment variable, endpoint, migration step, new project, removed feature.

Docs owned by someone else (a colleague's skills or READMEs, a vendored folder): report findings, change nothing without the user's yes. Check `git log` for who writes a file when it is not obvious.

**Large repos.** With more than about ten docs, split the check by project or module and give each part to a subagent with its own list of files to edit; do the root docs yourself and review every subagent's diff before committing.

**Where to commit.** Doc fixes belong on a branch of their own (or the docs branch the user named). If the working tree has someone's uncommitted work, never commit it with the docs: create the branch without touching their files when git allows it, otherwise ask the user before stashing anything, and put their work back exactly as it was. Never push without the user's yes.

## 2. Check every claim

Go through the docs sentence by sentence and verify each concrete claim against the repo:

| Claim | How to check |
|---|---|
| A path, project, class, file or script | It exists (`Glob`, `Grep`). |
| A command (build, test, run, migrate, lint) | It matches CI, the scripts and the project files; run it when it is cheap and safe (`--help`, a build, a single test project). Never run anything against a shared database or deploy. |
| A version (SDK, framework, Node, package) | `global.json`, `*.csproj`, `Directory.*.props`, `package.json`, CI images. |
| A setting, secret name or environment variable | The config files and the code that reads it. Never copy a secret value into a doc. |
| A branch, base branch or release step | `git branch -r`, CI triggers, recent tags. |
| A rule ("never X", "always Y") | Still matches what the code and recent commits do; if the code now does otherwise on purpose, ask the user which is right. |
| A convention (commit style, branch names) | `git log` and `git branch -r` of this repo, not the user's global rules. |
| Something in another repo, or in a skill or file that is not in git (ports, scripts, accounts) | Read that repo or file; a doc that depends on it must say where it comes from. |
| A link | The target exists relative to the doc's own folder. |

Scripts next to a skill's `SKILL.md` are part of the skill: fix them when the doc and the script disagree, and run the script if that is safe.

Mark each claim: **ok**, **wrong** (with what is true now), **stale** (refers to something gone) or **unverifiable** (say why).

## 3. Find what is missing

- How to build, test and run the app locally. If running is not documented and there is no `run-*` skill, say so and suggest creating one (the `verify-app` skill uses it).
- Projects, apps or submodules the docs do not mention.
- Traps the git history shows people keep hitting (repeated fix commits for the same build or setup problem).
- In branch mode: anything the change added that the next person needs to know (new setting, new migration, new command).

## 4. Fix

- Show the findings as a short list with file and line, then edit.
- Keep the docs short and in the existing language and style; keep the user's wording where it is still true. Correct a sentence instead of adding a second one about the same thing. Do not narrate what the code says.
- Never write secrets, personal data or machine-specific values (local ports, absolute paths, user names) that are not already the documented convention. Such values belong in the user's own notes (`CLAUDE.local.md`, a personal recipe), not in a doc in git.
- A secret already in a doc: replace it with a placeholder and tell the user it must be rotated. A secret in code or config: report it to the user (file and key, never the value); do not describe the leak in the docs.
- Doc changes go in their own commit, separate from code changes, following the repo's commit style and the git guide's commit mode.

## 5. Report

One line per changed file with what changed, then the claims that stayed unverifiable and why. In branch mode, say "docs are up to date" when nothing needed changing.
