---
name: pr-walkthrough
description: Walks the user through someone else's pull request so they understand it before reviewing it. Explains in plain words what problem it solves, what changes before and after, takes a short tour of the few places in the code that matter in reading order, explains the domain terms and points at where the risk is. Reads only; posts nothing. Uses the pr-review setup (repo list, local clones, repo notes). Use when the user runs /pr-walkthrough, or asks what a PR does or to explain a PR.
---

# PR walkthrough

- `/pr-walkthrough [repo] <number>`: the whole PR; when there is an earlier walkthrough, only what changed since.
- `/pr-walkthrough [repo] <number> full`: the whole PR again.

It needs the `pr-review` setup: the repo list in `config.local.ps1` (`/pr-review postavi` writes it), local clones, and the optional repo notes `repos\<repo>.md`. Write in the language the user writes in.

This is not a review. No findings, no comments to post, no build, no tests. The goal is that after reading it the user can explain the PR to someone else.

## 1. Gather

1. Harvest as `pr-review` does, and stop with its message if it returns `{error}`:
   `pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-harvest.ps1" -Repo <repo> -Pr <n> -ScratchDir "<scratchpad>"`
2. Fetch the PR branch without checking it out: `git -C <localPath> fetch origin <dest> <fetchSpec>`. Read files with `git show pr-<n>:<path>`; the user's checkout stays on its own branch.
3. The ticket, if `ticketKey` is set and a tracker connector is available. Without it, say in one line that the ticket was not read.
4. The repo notes (`notesPath`), especially their `## Terms` section.
5. An earlier walkthrough `<reviewsDir>/<repo>-<pr>.walkthrough.md`: its first line holds the head it was written for. If the PR moved on since and the mode is not `full`, write only the "What changed since" part (step 3) for `<old head>..pr-<n>`.

## 2. Understand before writing

Read the whole diff and enough of the surrounding code to answer, for yourself:

- What did the code do before, and what does it do now? Which user, device or process notices the difference?
- Where does the change start (an endpoint, a UI event, a job, a message) and which path does it take?
- Which three to five places carry the actual idea? Renames, formatting, generated files and plumbing are not among them.
- Which terms would a capable developer new to this domain not know?
- Where can it break: shared state, concurrency, transactions and locks, migrations, error paths, external calls, time zones?

If something stays unclear after reading the code, it becomes a question for the author, not a guess.

## 3. Write

Save as `<reviewsDir>/<repo>-<pr>.walkthrough.md`, first line `<!-- walkthrough <repo>#<pr> @ <headSha> -->`, and show it the way the user's rules say documents are shown. It fits on about two screens:

1. **In one sentence**: what the PR does.
2. **Why**: the problem, from the ticket and the code. When the title is all there is, say what the code shows.
3. **Before and after**: one concrete example of behavior, for example "the operator pressed Stop and the step kept running until it finished → now it stops within a second and the result is marked Cancelled".
4. **Tour of the code**: three to five stops in reading order. Each: `path:line` in the PR branch, two or three sentences on what happens there and why, and an excerpt of at most ten lines when it helps. Big PRs: group by area, keep at most six stops, and name the rest in one line.
5. **Terms**: one line each, only the ones this PR needs.
6. **Where to look carefully**: one to three places where a mistake would hurt, each with the reason. These are pointers for the review, not findings.
7. **Open questions**: what the code does not answer, phrased so it can be asked to the author as is. Leave the section out when there are none.

For a walkthrough of changes since the last one, the document is: what the author changed since `<old head>` (commits and files), which earlier open questions this answers, and new stops for new code only.

## 4. After

- In the chat: the one-sentence summary and an offer to answer questions or go deeper into any stop.
- Terms that are not in the repo notes yet: list them and, on a yes, add them to the `## Terms` section of `repos\<repo>.md` (create the file if missing; git ignores it). The notes then explain the domain better with every PR.

## Never

- Post anything on the PR or the ticket.
- Check out the PR branch in the user's working tree.
- Present a guess about intent as fact: the reason comes from the ticket, the description or the code, and otherwise is an open question.
