---
name: power-market-domain
description: Use when implementing Example Province electricity market modules, hydro generation scenario logic, Demo Hydro A assumptions, market data schemas, policy interpretation, 96-point day-ahead analysis, or trading recommendation logic for this project.
---

# Power Market Domain

Build a human-reviewed Example Province power-market intelligence and hydro
trading-advice system.

## Boundaries

- Do not implement live trading execution, order submission, or trading-platform
  login automation.
- Treat LLM output as explanation, extraction, or review support. Do not let an
  LLM alone decide numerical trading actions.
- Clearly label company-side data as public, derived, simulated, or uploaded.
- Never present Demo Hydro A scenario data as verified internal company data.

## Domain Defaults

Focus on:

- Example Province electricity market intelligence.
- Day-ahead and real-time spot-market context.
- Medium- and long-term contract exposure when data is available.
- Daily 96-point intervals.
- Hydro generation company perspective.
- Demo Hydro A as the default scenario hydro asset.
- Public policy and rule monitoring.
- Evidence-backed, human-reviewed recommendations.

## Recommendation Object Requirements

Every recommendation must include:

- trade date and horizon
- data mode
- scenario assumption id when simulated
- market view
- recommended windows or actions
- risk level
- confidence score
- missing data warnings
- structured evidence
- human review required flag
- explicit no-auto-trading flag

## Separation Of Concerns

When implementing strategy logic, separate:

1. Input data collection and validation.
2. Feature calculation.
3. Forecast result.
4. Rule or optimization logic.
5. Recommendation assembly.
6. LLM explanation, if used.
7. Compliance check.
8. Human review and feedback.
