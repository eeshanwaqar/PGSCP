# Runbooks

Operational playbooks for known conditions. Every alarm in CloudWatch should link to exactly one runbook here.

| Runbook | Trigger |
|---|---|
| [template.md](template.md) | — (starting point for new runbooks) |
| `deploy.md` | Normal deployment procedure (planned) |
| `rollback.md` | Deployment unhealthy, need to roll back (planned) |
| `partner-outage.md` | Partner API failure-rate alarm (planned) |
| `queue-backlog.md` | SQS `ApproximateNumberOfMessagesVisible` alarm (planned) |
| `db-access-issue.md` | RDS connection pressure or reachability alarm (planned) |

Runbooks are written in Phase 6 of the implementation plan, after observability is wired up — they reference dashboards and CloudWatch Logs Insights queries that don't exist yet.
