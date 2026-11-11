---
paths:
  - "**/*.cs"
---

# C# / .NET guide

Read this before writing or reviewing C# code. General rules in AGENTS.md still apply.

When a project already has its own convention (`.editorconfig`, constant casing, test framework, mapping library, data access pattern, error handling style), follow the project. The rules below are the default for new code and new projects.

## Formatting

- Allman braces, 4-space indentation, file-scoped namespaces in new files.
- At most one blank line between members.
- Break long LINQ chains into one call per line, with the dot at the start of the line.
- Format only the lines you change. Do not reformat untouched code in the same file; whole-file formatting happens only when explicitly asked, as a separate commit.

## Naming

- Private fields are `_camelCase`.
- Constants are `SCREAMING_SNAKE_CASE` at the top of the class, unless the project already uses PascalCase.
- Long, descriptive method names are fine. The name should say what the method does, including side effects (for example `InsertServiceTypeIfMissingOrThrow`).

## Types and variables

- Use `var` by default. Write the explicit type only when it is not obvious from the right-hand side and matters for understanding.
- Enable nullable reference types in new projects. Do not use `!` to silence warnings, except for test fields initialized in setup.
- No tuple returns with three or more elements; use a small `record`.

## Control flow

- Always use braces for `if`, `else`, `for`, `foreach` and `while`, even when the body is a single line.
- Prefer guard clauses with early `return` / `continue` / `throw` over nested `if`/`else`; keep the main path unindented.
- Extract compound boolean conditions into a named local before the `if`.

## Async

- Add the `Async` suffix only when the same class also has a synchronous version of the method, so the two can be told apart. Otherwise use the plain name.
- Accept a `CancellationToken` in async methods that do I/O and pass it on to every call that accepts one.
- Never block on async code (`.Result`, `.Wait()`, `.GetAwaiter().GetResult()`) in new code.

## Errors and exceptions

- Follow the project's error handling style: if it uses result objects (for example `Response<T>.Success/Failure`), use them; otherwise throw exceptions.
- Never swallow an exception. A `catch` must either log it (passing the exception object to the logger) and handle it, or let it propagate. No `catch { throw; }` blocks, and no `return null` from a `catch` to hide a failure.
- Prefer the project's existing exception types over `new Exception(...)`.

## Data access

- Filter, sort and page in the database. Never load rows into memory and filter them there.
- Use `AsNoTracking()` for read-only EF queries.
- Use LINQ method syntax; query syntax is fine for queries with several joins.
- Give intermediate queries meaningful names (`activeReservationsQuery`, then `activeReservations = await ...ToListAsync()`).

## Mapping

- Hand-written mapping methods in new code. Use AutoMapper only where the project already does.

## Tests

- See `~/ai-config/rules/tests.md`.

## Comments and old code

- Few comments. Instead of explaining unclear code, rename or restructure it; a comment is for *why*, not *what*.
- Delete replaced code. Do not leave it commented out or renamed to `*Old`; git keeps the history.

## Method calls and constructors

- When a constructor has more than three parameters, use named arguments for every supplied argument. Put longer calls on separate lines so each value's meaning is visible.

## XML documentation

- Write an XML summary for every public method that contains business logic or has side effects.
- Method XML summaries should explain motivation first, behavior and side effects second, and a concrete example third. Separate those paragraphs with blank comment lines and `<para>` elements. Use plain language and explain the actual source, destination and values rather than vague terms.

Example:

```csharp
/// <summary>
/// Reservations imported from the partner feed arrive without a currency,
/// and the invoice generator rejects rows that have none.
/// 
/// <para>
/// Sets <c>Currency</c> on every reservation in the batch to the partner's contract currency.
/// Reservations that already have a currency are left unchanged.
/// Nothing is saved; the caller saves the batch.
/// </para>
/// 
/// <para>
/// Example: the partner's contract currency is EUR and the batch has three reservations,
/// one already in USD. After the call two are in EUR and one is still in USD.
/// </para>
/// </summary>
```
