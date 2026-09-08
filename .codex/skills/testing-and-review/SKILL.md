---
name: testing-and-review
description: Use when reviewing code, adding tests, validating migrations, checking crawler safety, checking security, preparing pull requests, or finishing a development task for this project.
---

# Testing And Review

Prefer narrow checks while iterating and broader checks before finishing a
substantial task.

## Required Checks

Run relevant commands:

```powershell
pytest
ruff check .
mypy .
```

If database models or migrations changed:

```powershell
alembic upgrade head
```

## Review Checklist

Check for:

- missing tests
- hardcoded secrets
- unsafe external requests
- missing timeout or retry
- missing logging
- missing error handling
- API schema mismatch
- migration mismatch
- simulated data mislabeled as real data
- unreviewed trading automation

## Security Rules

Never commit:

- API keys
- cookies
- credentials
- company trading data
- live account information

Reject or remove code that submits trades, automates trading-platform login, or
promotes models without human approval.
