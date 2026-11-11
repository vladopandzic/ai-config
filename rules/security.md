# Security guide

Read this before writing code that handles authentication, user data, files or configuration, and before adding a package.

## Secrets

- Never put secrets (connection strings, API keys, tokens, passwords) in code or in committed configuration. Locally use user secrets or environment variables; on servers use environment variables or a key vault. Committed `appsettings` files contain only empty keys or placeholders.
- If you find a secret in code or committed configuration, tell the user.

## Authorization

- Every controller or action makes an explicit decision: `[Authorize]` (with a role or policy where needed) or `[AllowAnonymous]`. Never leave an endpoint without one.
- When a record is loaded by id, check that the current user may access that specific record: filter the query by user, agency or tenant, or check ownership. If not allowed, return 404 so the record's existence is not revealed.

## Personal data

- Never write personal data (guest names, emails, phone numbers, documents, payment details), passwords or tokens to logs or error messages. Log ids instead (`ReservationId`, `GuestId`).

## Files, paths and URLs from clients

- Uploads: limit the size and the allowed file types, store the file under a generated name outside the web root, and never use the client's file name to build a path.
- Use file paths and outbound URLs that come from a request only after checking them against an allow-list.

## CORS

- Allowed origins come from configuration per environment. Never use `AllowAnyOrigin` in production, and never together with credentials.

## Packages

- Before adding a NuGet or npm package, tell the user which package, why, and whether it can be done without one, and wait for confirmation. Check that it is maintained and has no known vulnerabilities (`dotnet list package --vulnerable`, `npm audit`).

## Findings outside the task

- If you notice a security problem in existing code outside the current task, report what it is, where, and how serious it is. Fix it only if the user asks.
