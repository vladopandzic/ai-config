---
name: self-improve
description: Turns the user's repeated corrections into rules in the right file (shared AGENTS.md, personal AGENTS.local.md, a topic guide, a project CLAUDE.md or a skill), one proposal at a time with the user's approval. Use when the user runs /self-improve, or asks to review their corrections, learn from past sessions or improve the rules. "/self-improve" looks at this session, "/self-improve history [days]" at all projects.
---

# Self-improve

A rule is something the user repeats; a one-off "no, do it like this" is not. Look for corrections that recur, propose a rule for each, and write only what the user approves.

## Modes

- `/self-improve`: the current conversation.
- `/self-improve history [days]`: the user's messages from all projects, default 30 days.

## Find the files

The ai-config repo is where this skill really lives. Find it with PowerShell:

```powershell
(Get-Item "$env:USERPROFILE\.claude\skills\self-improve").Target
```

The repo is two folders up from that path. Read these before proposing anything, so you know what is already covered:

- `<repo>\AGENTS.md`, `<repo>\AGENTS.local.md`, `<repo>\CLAUDE.md`, `<repo>\rules\*.md`
- `%USERPROFILE%\.claude\CLAUDE.md`
- `<repo>\self-improve.local.md`: the decisions log (may not exist yet)

## Where a rule belongs

| The rule is… | File |
|---|---|
| good for everyone, colleagues included | `<repo>\AGENTS.md`, or `<repo>\rules\<topic>.md` when it is about one topic (C#, git, database, tests, API, security) |
| the user's own taste or workflow | `<repo>\AGENTS.local.md` (not in git) |
| true for one project only | that project's `CLAUDE.md` |
| about how one skill or command works | that skill's file |

Never write to `%USERPROFILE%\.claude\CLAUDE.md` unless the user asks for it.

## Session mode

1. Go through this conversation and collect:
   - corrections ("no", "don't", "I said", "again", or the same thing in the user's language),
   - tool calls the user rejected with a comment,
   - corrections right after a skill or command ran: these improve that skill.
2. Keep what would help in future work; drop one-off redirects about this task only.
3. Continue with "Proposals".

## History mode

1. Run the extract script, writing to the temp folder:

   ```powershell
   python "<repo>\skills\self-improve\extract.py" --days <days> --out "$env:TEMP\self-improve-messages.txt"
   ```

   It keeps messages that look like corrections; the filter is only a first cut, so judge meaning, not keywords.
2. If the file is under about 40 KB, read it yourself. Otherwise give it to one subagent with this task: read all of it plus the rule files above, group the messages by meaning, count how often each theme recurs, and return three lists with short quotes ("[date project] text") and counts:
   - **new**: not covered by any rule,
   - **covered but broken**: a rule exists and was still violated, so its wording needs to be stronger,
   - **project or skill**: belongs in one project's `CLAUDE.md` or in one skill.
3. Keep themes that recur at least twice, plus any rejected tool call with a comment and any single complaint that is clearly strong. Sort by count.
4. Drop what the decisions log says the user skipped, unless it recurred at least three times since; then propose it again and say it was skipped before.
5. Write the list as a document in the user's language, sorted by count, open it the way the user's rules say documents should be shown, and continue with "Proposals".

## Proposals

Go one at a time. For each proposal show:

- **What the user said**: the count and one or two short quotes.
- **The rule**: the exact text, ready to paste, in the language of the target file.
- **Where**: the target file and section.

Then let the user choose: write it, change it, or skip it. Do not show the next proposal until the user decides on this one.

After each decision, add a line to `<repo>\self-improve.local.md` (create it with a `# Self-improve decisions` heading if missing):

```
- 2026-11-12 | written | Keep answers short | AGENTS.md
- 2026-11-12 | skipped | Estimate cost before scheduling | -
```

## Writing

- Put the rule into the matching section of the target file; create a section only when none fits. Never append a generated block at the end of a file.
- Reword an existing rule instead of adding a second one about the same thing.
- If a file grows past about 150 lines, say so.
- Commit according to the git guide's commit mode.

## Never

- Send session content anywhere except the user's own Claude session.
- Write a rule the user did not approve.
- Quote more than a short line of any message.
