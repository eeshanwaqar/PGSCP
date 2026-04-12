# Postmortem: <short incident name>

- **Date**: YYYY-MM-DD
- **Authors**: who wrote this
- **Severity**: SEV1 | SEV2 | SEV3
- **Status**: Draft | Final
- **Duration**: HH:MM — HH:MM UTC (total: X minutes)

## Summary

One paragraph. What happened, in plain language. What the customer saw.

## Impact

- Who was affected and how many of them
- What functionality was degraded or unavailable
- Data loss: none / bounded / unknown
- Duration of impact

## Detection

- How did we find out? (alarm name, customer report, routine check, etc.)
- Time to detect (from start of impact to first human aware)
- Was the right alarm configured? Did it fire at the right threshold?

## Timeline

All times in UTC.

- **HH:MM** — Event that started the incident (deploy, traffic spike, dependency failure, ...)
- **HH:MM** — First symptom visible in metrics
- **HH:MM** — Alarm fired
- **HH:MM** — On-call acknowledged
- **HH:MM** — Root cause identified
- **HH:MM** — Mitigation applied
- **HH:MM** — Full recovery confirmed

## Root cause

The technical root cause, explained clearly enough that someone unfamiliar with this subsystem can understand it. Include any contributing factors (why was this possible to ship? what safety net didn't catch it?).

## Resolution

What actually fixed it, step by step. Include rollback commands, config changes, manual intervention.

## What went well

- Things that worked: fast detection, good runbook, clear ownership, useful logs, etc.

## What went poorly

- Things that hurt us: missing alarms, confusing dashboards, runbook out of date, etc.

## Corrective actions

| Action | Type | Owner | Due |
|---|---|---|---|
| Example: add alarm for X | Detection | @owner | YYYY-MM-DD |
| Example: fix validation bug | Prevention | @owner | YYYY-MM-DD |
| Example: update runbook step | Process | @owner | YYYY-MM-DD |

## Evidence

- Links to dashboards, CloudWatch Logs Insights queries, deployment IDs, traces, relevant commits.
