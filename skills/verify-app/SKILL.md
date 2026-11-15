---
name: verify-app
description: Proves a change works by running the real app locally and walking through it, with a screenshot for every step and a before/after pair for every changed screen. Writes the result in a fixed format (verify.json plus images) that other skills reuse, so a PR or a walkthrough can show what the change looks like. Only local apps and local or fake data; never touches shared environments. Use when the user runs /verify-app, asks to check a change in the running app, to take screenshots of a change, or when another skill needs proof that a branch or PR works.
argument-hint: "[branch | <repo> <PR> | ticket key] [what to check]"
---

# Verify app

Code review reads the code; this skill runs it. The output is evidence: what was checked, what happened and a picture of it.

## 1. What to verify

- **Target**: the current branch of the repo in the working folder, a branch name, or `<repo> <PR>` (resolve the repo and local clone the way `pr-review` does, from its `config.local.ps1`).
- **Base**: for a PR its target branch; for a branch `git merge-base HEAD origin/<default branch>`. The "before" side is that merge-base commit, not today's base branch.
- **Scenarios**: from the ticket's acceptance criteria, the PR description, or the user's words. Without them, derive them from the diff: every screen, field, column, button or message the diff adds, changes or removes is a scenario. Write each one as *action → expected result* before starting the app.
- A change with no visible diff (a package upgrade, a refactor): the scenarios are the main screens and calls that use what changed, and the expected result is "same as before".
- Changes with no screen (APIs, background jobs, migrations, libraries, CLI tools) are verified through the app's API, its tests, a CLI run or a read-back from the local database, recorded as `checks` (section 6) instead of images.
- An app that only signs in through single sign-on, with no development bypass or local test login: verify what has no screen (its API, SDK or tests) and record the screens as blocked.

## 2. Find how to run the app

Look in this order and use the first that exists:

1. A skill in the repo itself (`<repo>/.claude/skills/run-*` or the one the repo's `CLAUDE.md` names for running locally). Follow it exactly: it knows the SDK, the database, migrations and the test login.
2. The user's own notes for that repo in `recipes.local.md` next to this file (not in git).
3. The repo's docs and launch settings (`README`, `docs/`, `.claude/launch.json`, `Properties/launchSettings.json`, `docker-compose*`). Prefer a mode with fake or in-memory data and a development login bypass. When it works, offer to save it as a recipe (a repo skill, or `recipes.local.md` when the repo should not get one).

If the app cannot be started, stop and say exactly what is missing (SDK, database, secret, login). When this skill is a required step (for example in a finish-the-branch flow), that is a blocker, not something to skip.

## 3. Rules for running

- Never edit `appsettings*.json`, `global.json` or other tracked config to make the app start; use environment variables, user-secrets or a temporary copy. If a repo skill pins something temporarily, it also restores it.
- Run apps in the background and wait for the "listening" line or an HTTP 200, not a fixed sleep. Before starting, check who holds the port; another session's app may be running there. Note the process id or background task of everything you start.
- **Stop only what you started**, by the process id or task you noted. Never stop processes by name or by a path pattern: other sessions run the same tools from similar folders.
- Wait for the real content, not only for the spinner to go away: charts and grids can take seconds to fill, and an early screenshot looks like a regression.
- Only local databases or in-memory data. A local database that is a copy of real data is read-only except for what the scenario needs; put back every value you changed only for the test and record it under `cleanup`. The same goes for state outside the database (license files, registry values, local caches): save it before, restore it after.
- Pending migrations on the local database: show them and apply only after the user's yes, unless the repo's own skill says otherwise.
- Test logins come from the project's local configuration (user-secrets, a seed or example config) or a development bypass. Never type them into the chat, never use a real person's password for a shared system, never use single sign-on with a real account.
- Never point the app at a shared, staging or production environment.

## 4. Before and after

- **After**: the target branch. Build and run it from the repo when the working tree is on that branch and its uncommitted changes cannot affect the build (untracked files, docs, agent tooling), otherwise from an export: `git archive <head>` plus every submodule at its recorded commit, nested ones included. When the build itself calls git (`git describe` in a pre-build step), use `git clone --shared` and check out the commit instead.
- Put exports under a short path (for example `%TEMP%\v1`): deep scratchpad paths break tools limited to 260 characters.
- **Before**: the merge-base, exported the same way. The run recipe comes from the current checkout, not from the export: an older commit may not have the run skill yet. Point the recipe's build and start at the export folder; database checks and migrations still run from the checkout.
- Check that the "before" side can run before relying on it: the recipe's mode (fake data, login bypass) may be newer than the base commit, and old code may not match the local database's schema. If it cannot, record "before" as blocked, or pick another change when you were free to choose one.
- An old commit that no longer restores because of a newly published package advisory may be built with the audit relaxed on the command line for that build only (`-p:NuGetAudit=false` or `-p:WarningsNotAsErrors=NU1903`); write that into `notCovered`.
- Run "before" on a neighbouring port next to "after", or one after the other when the port is fixed (launch profile, sign-in redirect).
- Take the before/after pair from the same place on the same screen with the same data; keep the scroll position the same when the pages differ in length. Something removed gets a "before" image and an "after" note saying what replaced it.
- Delete the exported copies at the end.

## 5. Screenshots

- Use the built-in browser for localhost. When the session's folder has no launch configuration for the app, start the app in the background yourself and open its URL with `preview_start` and `url`. When the pane is hidden or narrow, emulate a desktop size with `resize_window` (for example 1280×800), take a shot and look at it; ask the user to show the pane only if the images are still wrong.
- **Mask personal data before every screenshot**: the signed-in user's name and email and any real customer data that is not needed to show the change. Define a small `__mask()` helper in the page with `javascript_tool`; define it again after every navigation. Component frameworks re-render after data loads and bring the real text back, so right before each shot: `__mask()`, wait a second, `__mask()` again, check that `document.body.innerText` no longer contains the masked values, then take the screenshot. Look at the image; if anything personal is still visible, take it again and never save the leaked one.
- Per step: act → wait until the page has settled (no loading overlay, faded form or spinner left) → check the state with `find` or JavaScript (screenshots can lag right after typing) → mask → screenshot.
- After clicking a checkbox, toggle or dropdown, confirm the new state in JavaScript. If a click through a ref did not change it, click the element's coordinates from a fresh screenshot. Copy the screenshot file into `img/` with a numbered name: `01-vehicle-settings-after.jpg`, `01-vehicle-settings-before.jpg`.
- Mark what the change added or changed: at most three rectangles per image, in percent of the viewport (`getBoundingClientRect()` / `innerWidth`, `innerHeight`), each with a number and a short label.
- Prefer clicking through `find` refs, taken right before the click in a separate call: component frameworks re-render and old refs go stale. Take coordinates only from a fresh full-scale screenshot.
- File uploads without an upload tool: build the file in the page and drop it with a `DataTransfer` event from `javascript_tool`; use made-up files, never real documents.
- Something you cannot reach (a dialog, a role you do not have, an external system): record it under `notCovered`. Never make up an image.

## 6. Output

Folder: `<reviews dir>\<repo>-<PR number or branch>.verify\`, where the reviews dir is `$ReviewsDir` from `pr-review`'s `config.local.ps1`, or `%USERPROFILE%\pr-review` without it. Replace the folder's previous contents on a new run.

`verify.json`:

```json
{
  "repo": "my-app",
  "target": { "branch": "ABC-123-short-name", "head": "<sha>", "pr": null, "ticket": "ABC-123" },
  "base": { "branch": "develop", "commit": "<merge-base sha>" },
  "app": { "name": "WebUI", "url": "https://localhost:5010", "recipe": ".claude/skills/run-local" },
  "verdict": "pass | fail | partial | blocked",
  "scenarios": [
    {
      "id": 1,
      "title": "New setting is on the vehicle screen",
      "expected": "Checkbox 'X' is shown and checked for existing vehicles",
      "actual": "Shown and checked",
      "verdict": "pass | fail | blocked",
      "shots": [
        { "side": "before", "file": "img/01-vehicle-before.jpg", "caption": "No checkbox before the change" },
        { "side": "after", "file": "img/01-vehicle-after.jpg", "caption": "New checkbox, checked by default",
          "marks": [ { "n": 1, "x": 12.5, "y": 40.1, "w": 20.0, "h": 4.2, "label": "New setting", "file": "src/Vehicle.razor" } ] }
      ],
      "checks": [
        { "side": "after", "kind": "http", "request": "GET /api/files/42/preview", "status": 404,
          "contentType": "application/problem+json", "log": "Preview file not found", "file": "logs/01-after.txt" }
      ],
      "evidence": "Saved off, reloaded, database value is 0; set back to 1"
    }
  ],
  "notCovered": [ "Mobile layout: pane was 630 px wide" ],
  "cleanup": [ "Vehicle 5 setting set back to on" ]
}
```

- `marks[].file` is optional: the source file behind the marked element, so a page that shows the code can link image and code.
- `checks` hold evidence without a screen: `kind` is `http`, `test`, `cli`, `db` or `log`, with the request or command, the status or exit code, and an optional text file under `logs/`. Keep statuses, counts and short log lines; never store response bodies, database rows or machine identifiers that can contain personal data.
- Verdict: `pass` when every scenario passed; `fail` when any failed; `partial` when something the change promised could not be checked; `blocked` when the app did not run. Things outside the change that were not checked go in `notCovered` and do not make the verdict partial.
- Also write `verify.md` in the user's language: verdict first, then each scenario with its images (a before/after table where there is a pair), then not covered and cleanup. That is the page a human reads; `verify.json` is for other skills. Write every caption so it says what the image shows: in a plain-text viewer the images do not render.

## 7. Report

Say the verdict in one line, then only the failed or blocked scenarios and why, and where the folder is. Open `verify.md` the way the user's rules say documents are shown.

## Never

- Change application code or commit anything. A failed scenario is a finding, not something to fix here; the calling flow decides.
- Use a shared, staging or production environment, or a real account through single sign-on.
- Leave apps running or exported copies behind.
