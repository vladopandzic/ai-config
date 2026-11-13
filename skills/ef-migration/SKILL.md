---
name: ef-migration
description: Adds, checks, removes and applies EF Core migrations in any .NET repo. Finds the right DbContext, project and migrations folder on its own, reviews the generated migration for data loss, catches migrations that clash with the base branch, and applies only to a local database after confirmation. Use when the user runs /ef-migration or asks to add, check, fix, remove or apply a database migration.
---

# EF migration

- `/ef-migration add <name or what changed>`: a new migration for every context the change touches.
- `/ef-migration check`: before a PR or after merging the base branch.
- `/ef-migration remove`: the last migration, while it exists only on this branch.
- `/ef-migration update [migration]`: apply to the local database.
- `/ef-migration script`: the SQL of this branch's migrations.

The database guide applies (`rules/database.md`): nothing runs against a database without the user's confirmation.

## Find the setup

Do this first in every mode, then report one line per context: context, project, migrations folder, startup project.

- **Contexts**: `git grep --recurse-submodules -nE "class \w+\s*(<[^>]*>)?\s*:\s*\w*DbContext\b" -- "*.cs"`. A context's migrations folder is the folder holding `<Context>ModelSnapshot.cs`, its project is the `.csproj` above that folder. A context with no snapshot has no migrations; leave it out.
- **Documented commands**: search `Makefile`, readme files, `CLAUDE.md`, `AGENTS.md` and the repo's own skills (`.claude/skills`, `.agents/skills`) for `dotnet ef`. A documented command wins: take its `--project`, `--startup-project`, `--context` and `--output-dir`. Run the `dotnet ef` command itself rather than the make target, so every argument is visible.
- **Startup project** when nothing is documented: none if the context has an `IDesignTimeDbContextFactory`; otherwise the executable project (`Microsoft.NET.Sdk.Web` or `<OutputType>Exe`) that registers the context with `MigrationsAssembly`.
- **Output folder**: the snapshot's folder relative to the project (`Migrations`, `Migrations/SqlServerMigrations`, `Migrations/ReportsDb`). Always pass `--context` and `--output-dir`; with several contexts in one project, EF otherwise picks wrong.
- **Tool**: with `.config/dotnet-tools.json` in the repo, run `dotnet tool restore` and the local tool is used. Compare `dotnet ef --version` with the project's `Microsoft.EntityFrameworkCore.Design` version: a tool with an older major version must be updated first; a newer one only prints a warning.
- **Build**: when `dotnet ef` only says "Build failed", run `dotnet build` on the startup project to see the error, and report it before anything else.
- **Submodule**: if `git -C <project folder> rev-parse --show-superproject-working-tree` prints a path, the project lives in a submodule and the migration belongs to that submodule's own repository and branch. Say so before doing anything; the parent repo only moves the submodule pointer.

## add

1. **Which contexts**: take the entities changed on this branch and in the working tree, and find each context whose model includes them (a `DbSet`, or a configuration applied in its `OnModelCreating`). When one entity is in several contexts, for example a server database and a local SQLite one, each needs its own migration; say so and add all of them.
2. **Base branch first**: run steps 1 and 2 of `check`. If the base branch has a migration for the same context that this branch does not have yet, merge the base branch first, or the new migration is built on an outdated snapshot.
3. **Name**: PascalCase, saying what changes, in the style of the latest names in that folder. When the user described the change, propose the name.
4. Run `dotnet ef migrations add <Name>` with the arguments from the setup.
5. **Read the generated migration** and check:
   - `Up` is empty: the context did not change, so it is the wrong context or the model change is missing. Remove the migration (see `remove`).
   - Changes the user did not make: an earlier migration was forgotten. Show them and ask whether they stay in this migration.
   - Data loss: `DropColumn`, `DropTable`, an `AlterColumn` that shortens a type or makes a column required, and a rename that EF wrote as drop plus add (change it to `RenameColumn` / `RenameTable`).
   - A renamed or dropped column or table: search the repo for the old name in raw SQL, views, stored procedures and reports, which EF does not update.
   - A new required column on an existing table without `defaultValue`: existing rows make it fail.
   - Index creation or a column type change on a big table: it locks the table while it runs.
   - Data changes (`migrationBuilder.Sql`, backfills): `Down` must undo them. If the repo has tests for data migrations, add one in the same style.
   - `Down` really reverses `Up`.
6. Summarize what the migration does in plain words, risky lines first.
7. If the project's docs list its migrations (a `CLAUDE.md` or readme with migration names), add the new one there.
8. Offer `update`; never apply it on your own.

## check

1. **Base branch**: the PR target if there is a PR, otherwise `develop`, then `main` or `master`. Run `git fetch` first.
2. **Clashes**: new migration files since the common ancestor, on each side:
   - on the base branch: `git diff --name-only HEAD...origin/<base> -- <migrations folders>`
   - on this branch: `git diff --name-only origin/<base>...HEAD -- <migrations folders>`

   When both sides added migrations for the same context: merge the base branch, remove this branch's migrations newest first (`remove`), and add them again. They then come after the base branch's migrations and the snapshot is correct. Never merge the snapshot by hand.
3. **Forgotten migration**: with EF Core 8 or newer, `dotnet ef migrations has-pending-model-changes` per context. With older versions, run the repo's own test for forgotten migrations if it has one; otherwise say this was not checked.
4. Report one line per context: clean, or what is wrong and the fix.

## remove

- A migration added in this session and never applied: delete its two files and, if the snapshot had no uncommitted changes before `add`, `git restore` the snapshot. No database is involved.
- Otherwise `dotnet ef migrations remove`. It connects to the database to see whether the migration is applied, so show the database first, as in `update`, and wait for a yes. If the migration is applied there, first `update` the local database to the migration before it, then remove.
- A migration that is already on the base branch, or pushed and possibly applied somewhere, is never removed. Write a new migration that reverses it.

## update

1. Show where it will run: `dotnet ef dbcontext info` prints the database and server, and `dotnet ef migrations list` shows which migrations are pending.
2. Local databases only: `localhost`, `(localdb)`, a local container or a SQLite file. For anything else, stop: there, migrations go through the project's release process.
3. Show the database and the pending migrations, wait for a yes, then `dotnet ef database update [migration]`.

## script

`dotnet ef migrations script <last migration on the base branch> --idempotent` with the context arguments and `-o` to the temp folder, never into the repo. Give the SQL as a ```sql block starting with `USE [database]`.

## Never

- Edit a snapshot or a `.Designer.cs` file by hand to resolve a conflict.
- Apply migrations to a database that is not local, or to any database without confirmation.
- Remove or rewrite a migration that is on the base branch.
