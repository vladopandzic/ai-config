---
name: prepare-pr
description: Gets the current branch ready for a pull request. Runs locally what the repo's CI runs (build, format, package consistency, tests), checks migrations and submodules, looks through the diff for leftovers, and drafts the PR description. Never pushes or opens the PR on its own. Use when the user runs /prepare-pr or says the branch is ready for review.
---

# Prepare PR

- `/prepare-pr`: the full run.
- `/prepare-pr quick`: tests only for the projects the branch changed.

Nothing here pushes, opens a PR or rewrites commits. Each of those is offered at the end and done only after a yes.

## 1. Branch

- Say the current branch and whether it is pushed. On `develop`, `main` or `master`, stop: the work belongs on a feature branch first.
- Base branch: the PR target if one exists, otherwise `develop`, then `main` or `master`. Run `git fetch` first.
- List the branch's commits and changed files against the base (`git log` / `git diff --stat origin/<base>...HEAD`).
- Uncommitted changes: list them and ask whether they belong in the PR. Do not commit them yourself.
- If the base has commits the branch does not, say how many and offer to merge it in before the checks, so they test what the PR will really contain.

## 2. Run what CI runs

Find the CI definition (`Jenkinsfile`, `bitbucket-pipelines.yml`, `.github/workflows/*.yml`, `azure-pipelines.yml`) and the repo's own PR target (`make prepare-pr` or similar). Run the same commands locally with the same flags. When CI and the PR target disagree, CI wins.

- **Test what the PR contains**: with uncommitted changes, run the checks in a clone of the branch in the temp folder (`git -c core.longpaths=true clone --no-hardlinks`), not in the user's working tree.
- **Same SDK as CI**: when CI pins a .NET version, pin it in the clone with a `global.json`. When CI runs on Linux and the matching image (`mcr.microsoft.com/dotnet/sdk:<version>`) is already local, run the step in it; ask before pulling an image.
- **Branch or base?** For every failure, look at the base branch's last CI run (`gh run list`, Bitbucket Pipelines or Jenkins). If the base passed there, run the same step on the base locally. Report failures the base has too separately from failures the branch causes.

- **Build** in CI's configuration and with its flags (`--configuration Release`, `--warnaserror`). A warning that breaks CI is a failure here too.
- **Format**: `dotnet format --verify-no-changes --include <changed files>`. It fails the PR only if CI or the PR target runs it; otherwise report it as a note. To fix, offer `dotnet format` on the changed files only, as a separate commit, so formatting does not mix with behavior changes.
- **Package consistency**: if CI runs `dotnet consolidate` or a similar check, run it too.
- **Tests**: first the test projects that cover the changed projects, then the whole suite unless the mode is `quick`. If the strict build fails, build normally and still run the tests, so their result is not lost. Integration tests that need Docker run only if Docker is up; otherwise say they were skipped.
- CI steps that cannot run locally (signing, installers, docker publish, deploy): skip them and list them in the report.

## 3. Migrations and submodules

- If the branch changes entities, a DbContext or a migrations folder, run the `ef-migration` skill's `check`.
- If a submodule pointer changed: the commit it points to must be pushed in the submodule's repository and merged into its base branch, or the PR points to a commit nobody else has.

## 4. Look through the diff

Read the whole diff against the base and list, with file and line:

- Leftovers: debug output, commented-out code, `TODO` without a ticket, skipped or focused tests.
- Secrets or machine-specific values: connection strings, tokens, local paths, a changed `launchSettings.json` or `appsettings.Development.json`.
- Changes unrelated to the ticket: they go to their own PR.
- A behavior change or bug fix without a test (the tests guide says when a test is needed).
- An API change that breaks existing clients: a removed or renamed endpoint, field or enum value.

This is not a review. For a full review, run `pr-review` on the PR once it is open.

## 5. Commits

- Messages follow the repo's style (the git guide). Point out commits that do not.
- `WIP` and `fixup` commits: offer to squash them, only if the branch has not been pushed yet. On a pushed branch this is a rewrite of history, so describe what changes and wait for an explicit yes.

## 6. PR description

Draft it in the language of the repo's commit messages, with:

- the ticket key, or a link if the tracker is known;
- what changed and why, in a few sentences;
- how it was tested: only what was actually run in step 2, plus what was skipped;
- risks: migrations, API contract, configuration, anything a deploy needs.

Write it to a temporary file and show it the way the user's rules say documents are shown. No mention of AI tools.

## 7. Report

One line per check: passed, failed with the fix, or skipped and why. Then offer, as separate questions: push the branch, open the PR with this description.
