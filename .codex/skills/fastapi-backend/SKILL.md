---
name: fastapi-backend
description: Use when creating or modifying FastAPI endpoints, Pydantic schemas, service modules, repository modules, SQLAlchemy integration, API tests, or backend error handling for this project.
---

# FastAPI Backend

Use a layered backend structure:

```text
backend/app/
  api/
  core/
  db/
  models/
  repositories/
  schemas/
  services/
```

## Rules

- API modules handle HTTP concerns only.
- Schemas define request and response contracts.
- Services contain business logic.
- Repositories contain database access.
- SQLAlchemy models must not be returned directly from API routes.
- Use dependency injection for sessions, settings, and clients.
- Add structured error responses for expected failures.
- Avoid broad exception swallowing.

## Endpoint Checklist

For each endpoint:

- Define Pydantic request and response schemas.
- Validate input boundaries.
- Return stable error shapes.
- Add tests for success and at least one failure path.
- Document important behavior in README or API docs when user-facing.

## Checks

Run the relevant subset:

```powershell
pytest tests/api
ruff check backend tests
mypy backend
```
