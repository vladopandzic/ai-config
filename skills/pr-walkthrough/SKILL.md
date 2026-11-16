---
name: pr-walkthrough
description: Walks the user through someone else's pull request so they understand it before reviewing it, as one self-contained HTML page. Explains in plain words what problem it solves and what changes before and after, takes a short tour of the few places in the code that matter in reading order, explains the domain terms and points at where the risk is; the page also shows every changed file with the diff, what kinds of things the PR touches, the PR's status and discussion, and pr-review findings when there are any. Claude only reads; the page's send button posts the user's own comments to GitHub or Bitbucket when the user picks them and clicks Send. Uses the pr-review setup (repo list, local clones, repo notes). Use when the user runs /pr-walkthrough, or asks what a PR does or to explain a PR.
---

# PR walkthrough

- `/pr-walkthrough [repo] <number>`: the whole PR; when there is an earlier page and the PR moved on since, only what changed (see Refresh).
- `/pr-walkthrough [repo] <number> full`: the whole PR again.
- `bez ekrana` after the number: no app run, the page has no Ekrani tab.

It needs the `pr-review` setup: the repo list in `config.local.ps1` (`/pr-review postavi` writes it), local clones, and the optional repo notes `repos\<repo>.md`. Tools: git, Python 3.11 or newer, PowerShell 7. Write in the language the user writes in; the page's own labels are Croatian.

This is not a review. No findings of your own, no comments to post, no tests. The app runs only through `verify-app`, for the Ekrani tab (section 4). The goal is that after reading the page the user can explain the PR to someone else.

The tools are in `tools\` next to this file (`<tools>` below). Run Python with `python -I`.

## Output

- The page: `<reviewsDir>\<repo>-<n>.walkthrough.html`, one file that works with a double click and can be sent to a colleague.
- Its data: `<reviewsDir>\<repo>-<n>.walkthrough\` (`<data>` below): the hand-written parts and the JSON the tools make, so the page can be rebuilt and refreshed.
- Screenshots: `<reviewsDir>\verify\`, written by `verify-app` (section 4).
- Never inside a repo. `reviewsDir` comes from the harvest.

## 1. Gather

1. Harvest as `pr-review` does, and stop with its message if it returns `{error}`:
   `pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-harvest.ps1" -Repo <repo> -Pr <n> -ScratchDir "<scratchpad>"`
   Save its JSON as `<data>\harvest.json` (UTF-8). Run it from PowerShell; from Bash its output can come back empty.
2. Fetch the PR branch without checking it out: `git -C <localPath> fetch origin <dest> <fetchSpec>`. This creates the local `pr-<n>`. The harvest has usually fetched it already, with the token for Bitbucket and Azure DevOps; fetch by hand only when `pr-<n>` is missing, because a plain fetch over HTTPS wants a login the machine often does not have. Read files with `git show pr-<n>:<path>`; the user's checkout stays on its own branch.
3. `head` = `git rev-parse pr-<n>`, `base` = `git merge-base origin/<dest> pr-<n>` (full shas).
4. The ticket, if `ticketKey` is set and a tracker connector is available. Without it, say in one line that the ticket was not read.
5. The repo notes (`notesPath`), especially their `## Terms` section.
6. An earlier page: `<data>\meta.json` holds the head it was built for. Same head → only refresh status, discussion and findings (steps 4 and 5). Different head and not `full` → Refresh below.

## 2. Understand before writing

Read the whole diff (`diffPath` from the harvest) and enough of the surrounding code to answer, for yourself:

- What did the code do before, and what does it do now? Which user, device or process notices the difference?
- Where does the change start (an endpoint, a UI event, a job, a message) and which path does it take?
- Which three to five places carry the actual idea? Renames, formatting, generated files and plumbing are not among them.
- Which terms would a capable developer new to this domain not know?
- Where can it break: shared state, concurrency, transactions and locks, migrations, error paths, external calls, time zones?

If something stays unclear after reading the code, it becomes a question for the author, not a guess.

## 3. Write the human parts

Everything here is short and in plain words; a class or file name appears only in `<code>` next to a human description. `tools\reference-template.html` shows every part filled with an invented example: copy its structure and classes, not its content.

`<data>\parts\`:
- `title.txt`: `PR walkthrough: <what the PR does in a few words>`.
- `header.html`: the `<header class="pr-head">` block with `<h1>` (what the PR does, five to eight words), `<p class="lead">` (one or two sentences with a concrete before → after) and `.pr-card-extra` (scope in one line: files, migrations, packages, tests). Branch, author, approvals, CI and the merge verdict are computed from the data; do not write them.
- `footer.html`, in this order:
  1. **Zašto**: the problem, from the ticket and the code. When the title is all there is, say what the code shows.
  2. **Prije i poslije**: one concrete example of behaviour in two `.card` blocks, for example "the operator pressed Stop and the step kept running until it finished → now it stops within a second and the result is marked Cancelled".
  3. **Na što paziti**: one to three `.watch` items where a mistake would hurt, each with the reason, a `<code>` file name and line, and a question for the author. The most important one is `li.top` with `<span class="tag">najvažnije</span>`. These are pointers for the review, not findings.
  4. **Pojmovnik**: a `<dl>`, one line per term, only the ones this PR needs.
  5. **Otvorena pitanja**: a second `.watch` list with what the code does not answer, phrased so it can be asked to the author as is. Leave it out when there are none.
- `iza.html` (optional): a diagram of at most six boxes with human names and verbs on the arrows, inline SVG as in the reference.

The tour of the code:
- `<data>\code-spec.json`: one panel per stop and per test worth showing (format in the docstring of `code_panels.py`). One to three line ranges of 3 to 20 lines in all, and `notes` = one sentence of at most ten words on the three to seven lines that matter. Code always comes from git; never retype it. `side: "base"` shows code the PR removed.
- `<data>\lanes.json`: the tour itself, shown as "Tura kroz kod". One lane per entry point, in reading order, three to five stops in all (big PRs: at most six, grouped by area):
  `[{"when": "Kad <what starts it>", "icon": "", "once": "<where it runs>", "steps": [{"text": "<what happens>", "panel": "<panel key>", "flag": "warn"?}], "evidence": [{"type": "test" | "note", "text": "...", "panel": "<panel key>"?}]}]`
  `flag: "warn"` marks a stop that belongs to "Na što paziti". Evidence is a test translated into a sentence, or a note on what was only read and not seen.
- `<data>\topics-human.json`: `summary` (one sentence per topic key that needs it, e.g. `tests`), `flags`, `items`, `highlights.tests` (tests as sentences, each with a panel). `{"summary": {}, "flags": {}, "items": [], "highlights": {}}` is valid.
- `<data>\outline.json` (optional): `{"_story": {"sentence": "..."}, "<path>": {"*": "<role of the file>"}}`; it marks key files in the file tree and gives "Pitaj Claude" its context.
- `<data>\zoom.json` (optional, for bigger PRs): the zoom levels from the story down to the code (Priča → Područja → Tok poziva → Slojevi → Arhitektura → Kod). Format:
  `{"layers": [{name, sub}], "classes": {key: {name, short?, file?, where?, layer}}, "areas": [{id, name, sum, classes: [], match: [path prefixes]}], "scenarios": [{id, name, area, steps: [{from, to, label, at: {cls, line, file?}, warn?: <number of a "Na što paziti" item>, note?}]}], "story": {"segments": [[text] | [text, areaId]], "before", "after"}}`.
  Every area needs at least one scenario; check every step's line against `git show <head>:<file>`.

Before building, print the line of every note and step from `git show <head>:<file>` and check it says what the text claims.

## 4. Ekrani: the app before and after

The Ekrani tab shows the changed screens from the running app, before and after, with the changed parts marked. It is built from `verify-app`'s result in `<reviewsDir>\verify\verify.json`.

- That file exists for this head (`target.head`): use it, do not run the app again.
- It is missing, the PR changes something a user sees (the `screens` topic in `topics.json`, or UI files in the diff) and the repo has a way to run (a `run-*` skill in the repo or a recipe in `verify-app`'s `recipes.local.md`): build and show the page without screens first, then run `verify-app <repo> <n>` and rebuild with them. Tell the user in one line that the screens are on the way.
- It exists for an older head: use it (the page says the screens may be out of date) and offer to run `verify-app` again.
- No way to run the app, no visible change, or `bez ekrana`: no Ekrani tab (delete an old `<data>\parts\ekrani.html`); say why in one line.

A mark on a screenshot opens the code panel of its `file`. Give every file the marks point at a panel in `code-spec.json` (the few lines that draw the marked part), also when it is not a stop of the tour; a mark without a panel cannot be clicked.

## 5. Build

```powershell
$T = "<tools>"; $D = "<data>"; $R = "<localPath>"
python -I $T\code_panels.py $D\code-spec.json $D\code-panels.json
python -I $T\verify_screens.py <reviewsDir>\verify $D\code-panels.json $R <base> <head> $D\parts\ekrani.html   # only with screens (section 4)
python -I $T\make_page.py $T\reference-template.html $D\parts $D\page-template.html
python -I $T\pr_topics.py $R <base> <head> $D\topics.json
python -I $T\pr_packages.py $R <head> $D\topics.json $D\topics-human.json
python -I $T\pr_meta.py $R auto <n> <base> <head> $D\meta.json $D\code-panels.json $D\topics.json
python -I $T\pr_sources.py $R <base> <head> $D\code-panels.json $D\sources.json
python -I $T\pr_status.py $R <base> <head> $D\harvest.json $D\prstatus.json
python -I $T\pr_discussion.py $D\harvest.json $D\discussion.json
python -I $T\pr_db.py $R <base> <head> $D\db.json --no-ai
python -I $T\build_page.py $D\page-template.html <reviewsDir>\<repo>-<n>.walkthrough.html CODE=$D\code-panels.json SOURCES=$D\sources.json OUTLINE=$D\outline.json PRINFO=$D\prstatus.json TOPICS=$D\topics.json HUMAN=$D\topics-human.json LANES=$D\lanes.json META=$D\meta.json DISCUSSION=$D\discussion.json DB=$D\db.json TONE="$HOME\.claude\skills\pr-review\references\ton-komentara.md" [ZOOM=$D\zoom.json] [DELTA=$D\delta.json] [FINDINGS=$D\findings.json]
```

- `pr_topics.py` finds from the diff what the PR touches (migrations, packages, settings, background jobs, external services, permissions, alerts, CI, screens, tests); its rules are for .NET. `pr_packages.py` adds where each changed NuGet package is used and its health from the public NuGet API (only package ids and versions are sent).
- `pr_db.py` builds the "Baza" view only when the PR changes an EF model snapshot. It reads PostgreSQL, SQL Server and SQLite snapshots; when the PR changes several DbContexts, each table name carries its context. Sample rows come only from a local PostgreSQL through the repo's user-secrets, read-only. Without `--no-ai` it asks Claude Code for example rows of tables the local database does not have; leave that to the user.
- `TONE=` puts pr-review's comment tone rules into the page, so "Predloži komentare" writes in the user's voice. The user's corrections to suggested comments go into that file as examples.
- Leave out an optional `NAME=` whose file does not exist; the page then hides that part.

Review findings: when `<reviewsDir>\<repo>-<pr>.findings.json` exists, copy it to `<data>\findings.json` and pass `FINDINGS=`. A findings file made for an older head still shows, with a note that the lines may have moved.

## 6. Check and show

- The build prints one placeholder per `NAME=`; zero means a wrong name.
- When a browser tool is available, open the page and read the console: no errors, and the dashboard, "Tura kroz kod", "Kod po temama", a code panel and, with screens, the Ekrani images show content. A page served from a temporary `python -I -m http.server --bind 127.0.0.1` works where `file://` does not; stop the server afterwards.
- Show the page the way the user's rules say documents are shown.

## 7. After

- In the chat: the one-sentence summary, the page path, and an offer to answer questions or go deeper into any stop.
- Terms that are not in the repo notes yet: list them and, on a yes, add them to the `## Terms` section of `repos\<repo>.md` (create the file if missing; git ignores it). The notes then explain the domain better with every PR.

## Review findings format

`pr-review` writes `<reviewsDir>/<repo>-<pr>.findings.json` (UTF-8) next to its manifest:

```json
{ "repo": "<owner>/<repo>", "pr": 42, "head": "<full sha that was reviewed>", "at": "<ISO UTC>",
  "verdict": { "merge": false, "approve": false, "why": "one sentence" },
  "findings": [{ "id": "F1", "manifest": 1, "lens": "bugs", "severity": "high",
    "kind": "inline", "file": "<repo-relative path>", "line": 344, "side": "head",
    "title": "the finding in a few words", "short": "one sentence", "plain": ["step by step, for someone new to the code"], "fix": "…",
    "proof": { "status": "red-test", "text": "the proof in a sentence", "output": "real output, shortened" },
    "blocksApprove": true, "resolved": false, "draft": "the comment text from the manifest, or null" }] }
```

`lens` is the lens file name without `.md`; `severity` high, med or low; `kind` inline or general (general: `file` and `line` null); `side` head or base; `proof.status` red-test, mutant, repro, measured, unverified or none; `replyTo` (a comment id) when the draft answers an existing thread; `manifest` is the `PR-COMMENT` number or null.

## Refresh

When the PR got new commits since the page was built:

1. Fetch again (step 1.2) and harvest again; the new head is `pr-<n>`.
2. `python -I <tools>\delta.py <localPath> <old head> <new head> <data>` writes `<data>\delta.json` (new commits, changed files and hunks, which panels and zoom steps sit on changed code) and moves `code-spec.json` and `zoom.json` to the new head, keeping `.bak` copies.
3. Write `summary` in `delta.json`: two to six sentences on what is new and why it matters for the review. Fix a tour text only when `stalePanels` or `staleSteps` say it went out of date.
4. Run step 5 again with the new head and `DELTA=<data>\delta.json`. The user's comments and saved answers in the page move with the code.

## Pitaj Claude (optional)

The page has ✦ next to every code line. It asks the viewer's own Claude Code through `tools\ask_server.py`, a small local helper (127.0.0.1, protected by a key it prints) that keeps one read-only session per PR on a copy of the PR's code. The page carries the helper and offers it for download, so a colleague who gets the page can use it too. Without the helper the page works fully and offers "Kopiraj pitanje" instead. Do not start the helper unless the user asks.

"✦ Predloži komentare" asks for comments on one file at the deep speed; each claim about other code must be checked there first and comes back with the file and line it rests on, and what could not be checked comes back as a question. "✦ Provjeri spremne" in Moji komentari checks every comment ready to post in one deep pass: whether it holds, repeats another comment or a pr-review draft, or contradicts another comment. A corrected text shows up next to the comment as Zamijeni / Zadrži moj. The result counts only for that text and that PR head.

"Pošalji na GitHub / Bitbucket" (in Moji komentari, the overview and Code review) opens a list of the user's unposted comments. The helper first reads what is already on the PR and marks comments that are there; ready comments are ticked, drafts and comments the check found wrong are not. Nothing goes out until the user clicks "Pošalji odabrane", and the helper refuses when the PR head moved past the page. GitHub posts through `gh` as whoever is logged in; Bitbucket uses pr-review's variables (`BITBUCKET_<WORKSPACE>_EMAIL`, `_TOKEN` to read, `_TOKEN_WRITE` to post). There is no button for Azure DevOps.

## Never

- Post anything on the PR or the ticket yourself; only the user's own click on the page's send button posts.
- Check out the PR branch in the user's working tree.
- Present a guess about intent as fact: the reason comes from the ticket, the description or the code, and otherwise is an open question.
- Put the user's own name, e-mail or accounts into the page; the harvest's `me` shows as "ti".
