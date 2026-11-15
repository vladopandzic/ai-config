---
name: contract-check
description: Checks that a change does not break the contract between apps that talk to each other, in both directions: an older client against the new server and the new client against an older server. Finds what the diff changes in DTOs, API routes, serializer settings, messages and shared schemas, lists every consumer, classifies each change as safe or breaking, and proves the risky ones with a round trip between the old and new code. Works on the current branch, any branch or an open pull request, whoever opened it. Use when the user runs /contract-check, asks whether a change is backward compatible or safe for older clients, or another flow (start-task sam, a review) changes something that crosses an app boundary.
argument-hint: "[branch | <repo> <PR>]"
---

# Contract check

A contract is everything one app sends and another reads: request and response bodies, routes and status codes, messages on a queue, files, and database tables that more than one app uses. Clients in the field update later than servers, and servers roll back, so a change has to work across versions.

## 1. Target and base

- The current branch, a branch name, or `<repo> <PR>` (resolve the repo, clone and PR branch the way `pr-review` does, from its `config.local.ps1`). A pull request opened by hand is checked the same way as one opened by a flow.
- Base: the PR's target branch, otherwise `git merge-base HEAD origin/<default branch>`. Old means the base commit, new means the head.

## 2. Find the contract surface in the diff

Look at the diff for:

| Changed | Examples |
|---|---|
| Types that cross a boundary | DTOs and models used in controller signatures, client SDK types, message and event classes, files written for another app |
| Serialization | JSON settings (`DefaultValueHandling`, naming policy, `TypeNameHandling`, enum as string or number, null handling), attributes (`[JsonProperty]`, `[DefaultValue]`, `[JsonIgnore]`, `[Required]`) |
| API shape | Routes, HTTP verbs, query and header names, status codes, API version, auth requirements |
| Shared storage | Tables or columns another app reads or writes, local databases that sync from the server |
| Packages | A client or SDK package version that consumers pin |

No contract surface in the diff: say "no contract change" and stop.

## 3. Find the consumers

Start from the repo's own notes: a "Contracts" section in `CLAUDE.md` or the docs (who consumes what, the oldest client still in use, serializer traps, how to run the other side's tests). When it is missing, find the facts as below and offer to write that section so the next check is faster.

For every changed surface, list who reads or writes it: other projects in the repo (`Grep` for the type, route or column), other repos named in the repo's `CLAUDE.md` or docs ("used by", client apps, SDK packages), and the oldest client version still in use when the docs or release tags say so. A consumer you cannot see (an outside partner, a mobile app not on this machine) goes in the report as "not checked".

## 4. Classify every change

| Change | Usually |
|---|---|
| New optional field, old readers ignore unknown fields | safe |
| New field whose default differs from the type's default (`bool X = true`) | risky: an old sender omits it and the reader gets the type default, or a serializer that skips default values drops it |
| Removed or renamed field, changed type, changed nullability | breaking for readers still using it |
| New enum value | breaking for old readers that fail on unknown values; check how they deserialize enums |
| Serializer setting changed | risky for every type it touches |
| Route, verb, status code or required header changed | breaking unless the old one still answers |
| New required field or new required validation | breaking for old senders |
| Column dropped or made non-nullable while an old app still writes it | breaking during rollout |
| The server now relies on a field that old clients never send | breaking: old clients get the default and the feature silently does nothing |
| Status or error code changed (500 → 404), including what a proxy passes through to a browser | risky for callers that branch on the status |
| Library signature changed (method, constructor, public type) | breaking for consumers on recompile; they see it when they move their submodule or package |

Check both directions for each change: **old consumer with new producer** and **new consumer with old producer** (a client updated before the server, or a server rolled back).

- **Which version is "old"**: what is really running or released on the other side (the deployed API, the released client, the submodule commit or package version the consumer pins), not just the base branch. For a library, compare the consumer's pinned commit with the new one, so breaking commits in between are not missed.
- **Only real callers count**: check that the old consumer actually calls the changed endpoint or type before proving compatibility for it.
- **When only the deploy order matters** (new API must be live before the new client), the proof is the order and the deploy history, written as a condition.

## 5. Prove the risky ones

Prove every change classified risky or breaking, and any "safe" one that touches serializer settings or defaults:

- **Round trip in code**: serialize a realistic payload with the old side and deserialize it with the new one in a small throwaway harness, both directions, through the same serializer settings each endpoint and client really uses, and compare the values that matter (especially defaults and false or empty values). Building the whole old version is not needed when the contract is a few types: compile the old versions of those files from the base commit next to the new build. Add a control case that shows the harness would catch the break (for example the payload without the field).
- **Running apps**: when both sides can run locally, use the repo's run recipe (see `verify-app`): the old client against the new server and the new client against the old server, one call or screen each.
- **Existing tests**: run the consumer's tests against the new producer when the repo has them. Tests that use a local database follow the run rules in `verify-app` (local only, put back what you change).
- **A package contract** (a client NuGet or npm package): compile the same small program once against the old and once against the new package version and pass the serialized data between them.
- **The other side cannot run** (an external service): compare old and new code on recorded responses or a characterization test.
- **Harness traps**: restore from the local package cache when a private feed is not reachable; polymorphic serializers (`$type`) need the old type in an assembly with the same name.
- **Reading the code** is a proof only when a run is not possible or not worth it (a default in a migration, a client without types or tests); mark it as `read` in the report so it is not mistaken for a run.

Use made-up data only. Delete harnesses and exports afterwards; never commit them. A missing test that would have caught a real breaking case is worth adding to the branch as a real test: say so, and add it only when the calling flow allows code changes.

## 6. Report

Write `contract.md` in the task folder that `pr-review/scripts/artifact-dir.ps1 -Repo <repo> -Key <key>` returns (`<reviews dir>\<client>\<repo>\<key>\`; the key is the ticket key, `PR-<number>` for a pull request, or the branch name when there is neither), and say in the chat:

- the verdict in one line: **compatible**, **compatible with conditions** (deploy order, a default, a flag) or **breaking**;
- a table: change · consumer · direction · result · proof (test name, harness output or "not proven, because …");
- what must happen before release (for example "deploy the server before the client", "add `[DefaultValue(true)]`");
- consumers that were not checked.

In a pull request flow, the verdict and the conditions go into the PR description.

## Never

- Change application code here, except adding a real test the calling flow asked for.
- Call shared, staging or production services to prove compatibility.
- Call something safe without a proof when it touches defaults or serializer settings.
