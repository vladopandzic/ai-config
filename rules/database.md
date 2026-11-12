---
paths:
  - "**/*.cs"
  - "**/*.sql"
---

# Database guide

Read this before writing queries, migrations or SQL. General rules in AGENTS.md and the language guide still apply.

## Project stack

- Follow the data access stack and layering the project already uses (EF Core, LinqToDB or Dapper; DbContext in services, repositories, UnitOfWork). Do not bring a different library or layer into an existing project.

## Reading data

- Filter, sort and page in the database. Never load rows into memory and filter them there.
- For reads, project into a DTO with `Select` and load only the columns you need. Use `Include` only when loading entities that will be changed and saved.
- Use `AsNoTracking()` for read-only queries that return entities.
- Never run a query inside a loop. Load the data for all items with one query (`Contains`, a join or grouping). Use `AsSplitQuery()` when including several collections.
- Any query that can return an unbounded number of rows (API lists, exports) is paged or limited with `Take`, with a stable `OrderBy`.

## Writing query code

- Use LINQ method syntax; query syntax is fine for queries with several joins.
- Give intermediate queries meaningful names (`activeReservationsQuery`, then `activeReservations = await ...ToListAsync()`).

## Saving changes

- One operation calls `SaveChanges` once. Use an explicit transaction only when several `SaveChanges` calls or raw SQL statements must succeed or fail together.

## Performance

The database is usually the bottleneck. For every new or changed query, think about how the database will execute it, not only whether it returns the right rows.

### Indexes

- When a query filters, joins or sorts by columns, check that a suitable index exists. If not, propose one in a migration and name the query it serves.
- In a composite index, put columns compared with `=` first, then range and sort columns.
- For frequent read queries that return few columns, consider a covering index (`INCLUDE` the selected columns).
- For queries that always target a subset of rows (for example `IsDeleted = 0`, `Status = 'Active'`), consider a filtered index.
- Every foreign key column has an index. EF adds them by convention; check schemas created by hand or through other tools.
- Do not add indexes blindly: each one slows down writes. Check existing indexes for overlap first.

### Query shape

- Keep predicates index-friendly: no functions or calculations on indexed columns in `WHERE`/`JOIN` (`x.Date.Date == today`, `x.Name.ToUpper()`, `Contains` with a leading wildcard). Rewrite as a range or a comparison on the raw column.
- Match parameter types to column types to avoid implicit conversions. On SQL Server, map `varchar` columns with `IsUnicode(false)` so EF does not send `nvarchar` parameters, which turn index seeks into scans.
- Use `AnyAsync()` to check existence, not `CountAsync() > 0` or loading rows.
- Keep transactions short. Never call external services (HTTP, mail) inside a database transaction.

### Large data

- For large tables or deep pages, use keyset pagination (`WHERE Id > lastId ORDER BY Id`) instead of `Skip` with a large offset.
- Update or delete many rows with set-based statements (`ExecuteUpdateAsync` / `ExecuteDeleteAsync`), not by loading entities and saving them one by one.
- Insert large volumes in batches or with bulk copy, not row by row.
- When `Contains` gets a very large list of ids (thousands), split it into chunks or use a temporary table.

### Verifying

- For non-trivial queries, show the SQL that will run (EF: `ToQueryString()`) and say which index it is expected to use.
- When a query is slow, look at the execution plan before changing code. Getting the plan from a real database counts as running SQL, so it follows the confirmation rule below.

## Raw SQL

- Use raw SQL only when LINQ cannot express the query or for a measured performance problem.
- Always parameterize it (`FromSql` / `ExecuteSql` with interpolation, Dapper parameters). Never build SQL by concatenating strings.

## Migrations

- After generating a migration, read it and summarize what it does. Call out anything that drops or renames columns or tables, or deletes data.

## Running against a database

- Before applying a migration or running any SQL against any database, show what will run and against which database, and wait for the user's confirmation, every time.
- Integration tests that create their own Testcontainers database are exempt.
- When giving the user SQL to run, give it as a ```sql block starting with USE [database], ready to paste into SSMS. Never wrap it in a sqlcmd command.
