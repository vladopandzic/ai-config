---
paths:
  - "**/*.cs"
---

# API guide

Read this before writing or reviewing HTTP APIs (controllers, endpoints, request and response models). General rules in AGENTS.md and the language guide still apply.

## Structure

- New projects use controllers. Existing projects keep their current style.
- Controllers are thin: an action receives the request, calls a service or handler, and turns the result into an HTTP response. Business logic and database queries belong in services, not in controllers.
- Actions accept a `CancellationToken` and pass it on to the service.

## Request and response models

- Never expose database entities through the API. Use separate request and response DTOs, so a database change does not change the API contract.
- Validate input with the approach the project already uses (FluentValidation or DataAnnotations).

## Errors

- Do not put `try/catch` in controller actions to build error responses. A global exception handler turns exceptions into responses:
  - entity not found → 404
  - invalid input → 400
  - business rule violated or conflicting state → 409
  - anything else → 500
- Error responses use `ProblemDetails` (`application/problem+json`), with validation errors listed in `errors`.
- Never send exception messages, stack traces or database errors to the client. Log them on the server; the client gets a generic message for 500.

## Status codes

- `POST` that creates a resource → 201 Created with a `Location` header.
- `PUT` / `PATCH` / `DELETE` that returns no body → 204 No Content.
- Requested resource does not exist → 404.
- Invalid input → 400.
- Conflict with the current state (duplicate, wrong status for this action) → 409.
- Not authenticated → 401; authenticated but not allowed → 403.

## API contract

- A change that can break existing clients must be called out and confirmed before you make it: renaming or removing a field, changing a field's type, adding a required field, changing a route or a status code. Adding optional fields is fine.
