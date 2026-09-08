---
name: quiz-app-architecture
description: Canonical architecture and reuse map for this quiz_app repository. Use before implementing or changing models, services, repositories, schemas, API routes, WebSockets, Celery tasks, AI/PDF processing, Telegram bot flows, integrations, shared helpers, or configuration.
---

# Quiz App Architecture

Use this skill as the primary project context for implementation work. Read [references/architecture.md](references/architecture.md) before searching broadly or designing a new component.

## Required Workflow

1. Identify the relevant domain and read its entries in the architecture reference.
2. Search the repository by responsibility and symbol before creating any model, service, repository, schema, helper, enum, background task, or integration. Search adjacent domains too; shared implementations are not always colocated.
3. Inspect the exact files and callers named by the reference. Treat the reference as a map, not a substitute for reading code that will change.
4. Reuse an existing public method or type when it satisfies the requirement. If it is close but insufficient, extend it and its existing tests/callers instead of adding a competing implementation.
5. Preserve the current layering: routes and transports call services; services own validation, orchestration, and transactions; repositories own persistence and aggregate queries; schemas define transport shapes; SQLAlchemy models define relational state.
6. Re-run searches after choosing an approach to confirm that no equivalent implementation, enum, DTO, task, manager, or integration already exists.
7. Update this skill whenever a change adds, removes, moves, or materially changes an architectural component or dependency flow.

## Strict Rules

- Never create duplicate models, parallel business logic, duplicate enums, or a second implementation of an existing integration.
- Reuse or extend existing implementations whenever possible, including imperfect ones that already own the responsibility.
- Respect current module boundaries, naming, relationships, dependency injection, async patterns, persistence choices, and transaction ownership.
- Do not infer architecture from desired design. Document and implement only what exists or what the current task explicitly changes.
- Do not treat empty or unmounted modules as implemented functionality. The reference labels these explicitly.
- Keep this reference concise and factual. When architecture changes, update paths, responsibilities, and dependency/reuse relationships in the same change.

## Search Targets

Search these roots before adding code: `app/models`, `app/services`, `app/repositories`, `app/schemas`, `app/api`, `app/websocket`, `app/workers`, `app/bot`, `app/utils`, `app/core`, and `migration/versions`.

