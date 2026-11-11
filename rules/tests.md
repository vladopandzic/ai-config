---
paths:
  - "**/*Tests.cs"
  - "**/*Tests/**/*.cs"
---

# Tests guide

Read this before writing or reviewing tests. General rules in AGENTS.md and the language guide still apply.

## When to write tests

- Bug fix: first write a test that reproduces the bug and fails, then fix the code and show that the test passes.
- New business logic: add tests for its boundaries and risky cases.
- Otherwise write tests only when asked.

## What to test

- Test risks and boundary behavior. Do not write tests that merely repeat getters, constructors or implementation details.
- Each test checks one behavior. Several asserts are fine when they describe the same outcome; group them with `Assert.Multiple`.

## Unit vs integration tests

- Anything that goes through the API or the database is tested with integration tests against a real database (`WebApplicationFactory` for APIs).
- Pure logic (calculations, rules, mapping) is tested with unit tests.

## Database in integration tests

- Use Testcontainers with the same database engine as production. Never use the EF in-memory provider or SQLite as a stand-in.
- Every test starts from a clean state: a fresh database per test, or per test class when setup is expensive and the tests do not change shared data.
- Put seed data in seeder helper classes instead of long inline setup in each test.

## Mocks

- Mock only external boundaries: HTTP clients, mail, third-party services and time (`TimeProvider`).
- Use the real implementation of the application's own classes and the real database.

## Frameworks and style (C#)

- Follow the test framework the project already uses. New projects use NUnit, NSubstitute and NUnit's `Assert.That(actual, Is.EqualTo(expected))`. Do not add FluentAssertions to new projects (it needs a commercial license from v8).
- Test names follow `Method_WhenCondition_ShouldResult`, for example `CreateReport_WhenNightsIsZero_ShouldSkipReservation`.
- Mark the sections with `// Arrange`, `// Act`, `// Assert`.
- Shared setup goes in `[SetUp]` / `[OneTimeSetUp]` and seeder classes, not copied between tests.

## Running tests

- Run the relevant tests before saying the work is done, and report how many passed and failed.
- If tests cannot run (for example Docker is not available for Testcontainers), say so explicitly. Never claim tests pass without running them.
