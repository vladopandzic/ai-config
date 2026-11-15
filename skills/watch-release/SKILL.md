---
name: watch-release
description: Watches a change on its way out and right after it lands. Follows the pipeline that a merged pull request, a pushed release tag or a deploy started until it finishes, then watches the deployed app for a while (health, errors, logs the team already has) and reports in one line whether it is healthy, with evidence when it is not. Read-only: never restarts, rolls back or redeploys anything itself. Works whether the pull request or release was made by a flow or by hand. Use when the user runs /watch-release, says "prati deploy / pipeline / release", merges a PR or pushes a release tag and wants to know it went well, or another skill (release, start-task) hands over after a merge or tag.
argument-hint: "[PR | tag | pipeline run | branch] [minutes to watch after deploy]"
---

# Watch release

The work is not done when the pull request is merged; it is done when the change runs well where it was deployed.

## 1. What started

Find what the trigger started from the repo's CI definition and the release docs:

- a merged pull request → the pipeline on the target branch for that merge commit;
- a pushed tag → the pipeline that reacts to that tag pattern;
- a branch push or a manual run → that run.

Tools by host: GitHub `gh run list` / `gh run watch`; Azure DevOps `az pipelines runs list` / `az pipelines runs show`; Bitbucket Pipelines REST; Jenkins through its REST API (`/job/<path>/<n>/api/json`, console text) with the credentials the repo docs name. Credentials come from the environment, never from the chat.

Without access to the CI system, follow what the pipeline leaves behind (many pipelines commit a release commit, a final tag or a merge-back that `git ls-remote` shows; Bitbucket and GitHub also expose build statuses on the commit): the final tag or merge-back appearing on the remote (`git ls-remote`), the published package or image tag, the version endpoint changing. With the user's OK, read the CI page in the browser where they are signed in. Say which of these you used.

The repo's `CLAUDE.md` or release docs may have a "Release and monitoring" section (pipeline, where it deploys, health and version URLs, which logs exist and whether they cost money). Use it first; when it is missing, find the facts in the CI file and code and offer to write that section so the next run is faster. Access details that are personal stay in the user's own notes, never in the repo.

**Ask before the trigger when you can.** When another skill hands over before the merge or tag push (for example `release` before pushing), ask the access questions then (CI link, which monitoring may be read, billed queries) and take the "before" baseline right away. Called afterwards, use the history of the same signals for the baseline.

## 2. Follow the pipeline

- Start a background poller that exits only when the run finishes, so you are woken up when it is done. Never end a turn with "I'll keep an eye on it" without one running.
- When it finishes: the result in one line. On failure: the failing stage, the first real error from its log (not the last line), and whether the same stage fails on the base branch's last run, so the user knows if this change caused it.
- Check what the pipeline was supposed to leave behind: the final tag, the merge-back of a release branch, the published package version, the image tag.

## 3. Watch after deploy

Pick the case first:

- **Nothing is deployed** (CI only builds and tests): stop after step 2 with "CI passed, nothing deployed".
- **A package, installer or desktop update is published**: healthy means the artifact is there with the right version (package feed, release page, update manifest, final tag); there is no server to watch.
- **Staged deploys** (an automatic stage, then a manual approval): watch the automatic stage, then report "waiting for approval to <stage>" and stop. Continue when the user says it was approved; never wait for days.
- **A server or site is deployed**: as below.

Signs that the new version is serving, best first: a version endpoint with the commit; the health endpoint plus deploy logs; for a static frontend the bundle hash in `index.html`; container or deploy logs. With none of these, report "released, rollout not observable" and suggest adding a version endpoint. Plain GET requests to documented public health, version or index pages are fine; anything that needs credentials or is not documented needs the user's OK first.

For a deployed server or site, the watch window starts when the new version is really serving, not when the pipeline ends: when the pipeline only publishes or retags an image and something outside the repo rolls it out, poll the version or health endpoint until it reports the new version or commit, and start from there (say so if it never switches). The "before" window is the same length just before that moment. Watch for the time given (default 30 minutes), read-only:

- **Health**: the app's health or version endpoint answers and reports the new version or commit.
- **Errors**: compare the error rate in the watch window with the same length of time before the deploy, and look for exception types that did not exist before. Use what the team already has and the docs name: error tracking, log search, metrics or dashboards.
- **The change itself**: when the ticket or PR says what to look for (a new endpoint, a job, a migration), check that it shows up or ran.

Rules:

- Read-only on every shared, staging and production system: no restarts, rollbacks, redeploys, feature-flag flips or data changes, even when something looks broken. Report it and let the user decide.
- Monitoring that is billed per query (log search priced per scanned data, paid APIs) falls under the money rule: say what it would cost and ask before querying. Prefer free signals: health endpoints, the pipeline's own logs, dashboards that already exist.
- Production access is approved per task: if the docs do not say which monitoring may be read, ask the user once which sources are allowed.
- Never copy personal data or secrets from logs into the chat or a file; quote the exception type, message template and counts.

## 4. Report

- Healthy: one line with the version, where it runs and how long it was watched.
- Not healthy: what is wrong, since when, the evidence (counts before and after, the new exception, the failing check) and the likely link to the change, then the options (rollback, hotfix, feature flag off) for the user to choose. Say it right away; do not wait for the window to end.
- Could not watch (no access, no monitoring): say what was checked and what was not.

## Never

- Roll back, restart, redeploy, scale or change configuration anywhere.
- Query billed monitoring without the user's yes.
- Stop watching silently: the user always gets the final line.
