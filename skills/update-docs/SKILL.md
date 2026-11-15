---
name: update-docs
description: Keeps a repo's instructions for agents and developers true, well organised and getting better with every task. Checks CLAUDE.md, AGENTS.md, repo skills, reference docs and README build/run sections against the repo as it really is and fixes what is wrong, stale or missing; keeps the root CLAUDE.md short and puts details into topic references; after a task, records what the task taught and promotes the lessons that earned it into the right file, pruning what no longer helps. "/update-docs" audits and reorganises the whole repo; "/update-docs branch" checks what the current branch made outdated and learns from it, as a step before a pull request. Use when the user runs /update-docs, asks to update, check or reorganise CLAUDE.md or the docs, or a finish-the-branch flow needs the docs to match the change.
argument-hint: "[branch]"
---

# Update docs

Docs that agents read are only useful while they are true, short enough to be read and placed where they are needed. This skill keeps them that way and lets them improve with every task, without growing into a pile of one-off details.

## 1. Layout

Each repo's agent docs follow this layout; create it the first time and keep it.

| Place | What goes there | Size |
|---|---|---|
| Root `CLAUDE.md` | Rules that hold everywhere in the repo, how to build, test and run in a few lines, and pointers to the references | about 100 lines at most |
| `CLAUDE.md` in a subfolder | Rules that hold only for that part of the code (loaded only when an agent works there) | short |
| `docs/agents/<topic>.md` | References read when the topic comes up: `contracts.md`, `release.md`, `running.md`, and domain topics (validation, access rules, a protocol, a data model) | one topic per file |
| `docs/agents/learnings.md` | Candidate lessons from tasks that have not earned a place yet (section 4) | pruned regularly |
| `.claude/skills/run-*` and other repo skills | Procedures with steps and scripts | |
| `AGENTS.md` | The same content as `CLAUDE.md` for other agents; keep it in sync or make it a pointer | |

Root `CLAUDE.md` points to each reference with one line saying when to read it ("Changing a DTO, route or message: read `docs/agents/contracts.md`"). Never import references into `CLAUDE.md` (that loads them every time).

If the repo already keeps such docs elsewhere and the team uses that place (`docs/`, a wiki folder), use it instead of creating `docs/agents/`, and say so.

## 2. Scope

- **`/update-docs`**: every agent and build doc in the repo: `CLAUDE.md` and `AGENTS.md` at any level, `docs/agents/`, `.claude/skills/*/SKILL.md`, `.claude/rules`, and the build, test and run sections of `README` and `docs/`. Also reorganise them into the layout above.
- **`/update-docs branch`**: the diff of the current branch against its base (`git diff origin/<base>...HEAD`): docs that describe something the diff touched (a renamed project, command, setting, environment variable, endpoint, migration step, new project, removed feature), plus learning from the task (section 4).

Docs owned by someone else (a colleague's skills or READMEs, a vendored folder): report findings, change nothing without the user's yes. Check `git log` for who writes a file when it is not obvious.

**Large repos.** With more than about ten docs, split the check by project or module and give each part to a subagent with its own list of files to edit; do the root docs yourself and review every subagent's diff before committing.

**Where to commit.** Doc fixes go in their own commit: on the task's branch in branch mode, otherwise on a branch of their own (or the docs branch the user named). If the working tree has someone's uncommitted work, never commit it with the docs: create the branch without touching their files when git allows it, otherwise ask the user before stashing anything, and put their work back exactly as it was. Never push without the user's yes.

## 3. Check every claim

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

Mark each claim: **ok**, **wrong** (with what is true now), **stale** (refers to something gone) or **unverifiable** (say why). Also find what is missing: how to build, test and run (suggest a `run-*` skill when there is none), projects or submodules nobody mentions, and traps the git history shows people keep hitting.

## 4. Learn from the task (branch mode)

After a task, collect what it taught, starting from its task folder (`pr-review/scripts/artifact-dir.ps1`: the plan, review findings, contract and app checks and `run-log.md` when the flow wrote one): findings of `plan-review` critics that had to be dug out of the code, `pr-review` findings, `contract-check` and `verify-app` results, build or test traps hit on the way, and corrections the user or reviewers made on the pull request. For each lesson:

1. **Write it as a rule**, not a story: what to do or avoid, where, and why in a few words, with its source (ticket key or commit).
2. **Decide its place**:
   - **promote now** to its place in the layout when it would have changed a decision, cannot be seen quickly in the code, and either costs a lot when missed (data, money, security, production, a breaking contract) or is already in `learnings.md` from an earlier task;
   - otherwise **add it to `learnings.md`** as a candidate, or bump the count of the same candidate already there.
3. **Merge before adding**: if the topic is already covered, sharpen that sentence instead of writing a second one.

Do it in the same doc commit as the rest. The lessons are reviewed with the pull request, so no extra step is needed.

## 5. Keep it lean

Every run, in both modes:

- Keep root `CLAUDE.md` within its size: move details that are not repo-wide into a reference or a subfolder `CLAUDE.md`.
- Prune `learnings.md`: drop candidates older than about three months that never came up again, and those the code has made obsolete.
- Remove rules and references that are stale or that describe what the code already says plainly.
- One topic in one place: no duplicates between root, subfolders and references.

## 6. Fix

- Show the findings as a short list with file and line, then edit.
- Keep the docs short and in the existing language and style; keep the user's wording where it is still true. Do not narrate what the code says.
- Never write secrets, personal data or machine-specific values (local ports, absolute paths, user names) that are not already the documented convention. Such values belong in the user's own notes (`CLAUDE.local.md`, a personal recipe), not in a doc in git.
- A secret already in a doc: replace it with a placeholder and tell the user it must be rotated. A secret in code or config: report it to the user (file and key, never the value); do not describe the leak in the docs.
- Doc changes go in their own commit, separate from code changes, following the repo's commit style and the git guide's commit mode.

## 7. Report

One line per changed file with what changed, the lessons promoted and the ones added to `learnings.md`, then the claims that stayed unverifiable and why. In branch mode, say "docs are up to date" when nothing needed changing.
