# Global user preferences

## Code readability

- Write code that a reader can understand without guessing what a value, name or method means. Prefer explicit domain names over vague names, abbreviations and clever code.
- Keep methods short and focused on one responsibility. Extract meaningful steps when that improves reading; do not create helpers that merely hide an obvious expression.
- Organize code by real responsibilities. Do not add classes, abstractions or files just to split code. Related small helpers may share a file with the concept they support; one class per file is not a goal in itself.
- Avoid magic strings in application logic. Centralize configuration/protocol keys, use enums for closed sets, and convert and validate external strings at the boundary. Do not use human-readable messages as control-flow signals.
- When a name in code directly represents a database table or column, keep the actual name from the database schema (in whatever language it is) instead of a loose translation. State the exact mapping in documentation.
- Keep production behavior unchanged during naming/documentation refactors unless a behavior change is explicitly part of the task.

## Language and topic guides

Before writing or reviewing code, read the guide that applies:
- C# / .NET → `~/ai-config/rules/csharp.md`
- Tests (when to write them, what to test, frameworks, running) → `~/ai-config/rules/tests.md`. Read it also when fixing a bug or adding business logic, because those changes need tests.

## Effort and shortcuts

- Writing and rewriting code is cheap for you; do not ration effort as if it took a human days. Never pick a worse solution because the proper one "would take too long".
- The costs that matter are the user's review time and the risk of changing production behavior — not the amount of code you have to type.
- Do not leave workarounds, hacks, `TODO`s or "for now" solutions silently. If you take a shortcut, say so explicitly and explain what the proper solution would be.
- If the proper solution is much larger in scope than the task (many files, behavior changes), describe it and ask — scope is the user's decision, effort is not a reason.
- When asked for a time estimate, estimate your own working time, separately from the time the user needs to review and test.

## Git commits

- Never add "Co-Authored-By" lines to commit messages.
- Never add any AI attribution (Claude, Codex or similar) to commit messages.

## Git branches

- Never let a new feature branch track `origin/master` (or `origin/main`). After `git checkout -b NEW origin/master` (or any similar command), Git sets the new branch to track master — a future bare `git push` or `git pull` would hit master. Immediately run `git branch --unset-upstream <NEW>`, or use `git switch -c NEW --no-track origin/master` from the start. The branch should only get an upstream when it is first pushed with `git push -u origin NEW`, which points it at its own remote.
