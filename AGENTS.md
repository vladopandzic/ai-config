# Global user preferences

## Personal preferences

- If `~/ai-config/AGENTS.local.md` exists, follow it too. It is not in git and holds the machine owner's own way of working (language, tone, tools). Where it conflicts with this file, it wins. If it is already in your context, do not read it again.

## Code readability

- Write code that a reader can understand without guessing what a value, name or method means. Prefer explicit domain names over vague names, abbreviations and clever code.
- Keep methods short and focused on one responsibility. Extract meaningful steps when that improves reading; do not create helpers that merely hide an obvious expression.
- Organize code by real responsibilities. Do not add classes, abstractions or files just to split code. Related small helpers may share a file with the concept they support; one class per file is not a goal in itself.
- Avoid magic strings in application logic. Centralize configuration/protocol keys, use enums for closed sets, and convert and validate external strings at the boundary. Do not use human-readable messages as control-flow signals.
- When a name in code directly represents a database table or column, keep the actual name from the database schema (in whatever language it is) instead of a loose translation. State the exact mapping in documentation.
- Keep production behavior unchanged during naming/documentation refactors unless a behavior change is explicitly part of the task.

## Comments

- Very few comments. The code itself carries the meaning; if it can't, rename or restructure until it can.
- Never narrate what the code already says.
- Multi-line "why" explanations belong in the commit message or PR description, never in source files.

## Language and topic guides

Before writing or reviewing code, read the guide that applies:
- C# / .NET → `~/ai-config/rules/csharp.md`
- Tests (when to write them, what to test, frameworks, running) → `~/ai-config/rules/tests.md`. Read it also when fixing a bug or adding business logic, because those changes need tests.
- Database (queries, migrations, raw SQL, running anything against a database) → `~/ai-config/rules/database.md`
- HTTP APIs (controllers, DTOs, errors, status codes) → `~/ai-config/rules/api.md`
- Git (commits, branches, push, pull requests) → `~/ai-config/rules/git.md`. Read it before any commit, branch, push or PR.
- Security (secrets, authorization, personal data, uploads, CORS, packages) → `~/ai-config/rules/security.md`. Read it before writing code that handles auth, user data, files or configuration, and before adding a package.

## Effort and shortcuts

- Writing and rewriting code is cheap for you; do not ration effort as if it took a human days. Never pick a worse solution because the proper one "would take too long".
- The costs that matter are the user's review time and the risk of changing production behavior — not the amount of code you have to type.
- Do not leave workarounds, hacks, `TODO`s or "for now" solutions silently. If you take a shortcut, say so explicitly and explain what the proper solution would be.
- If the proper solution is much larger in scope than the task (many files, behavior changes), describe it and ask — scope is the user's decision, effort is not a reason.
- When asked for a time estimate, estimate your own working time, separately from the time the user needs to review and test.
