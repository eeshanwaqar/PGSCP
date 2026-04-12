# Runbook: <short name>

- **Trigger**: which CloudWatch alarm fires this runbook, and at what threshold
- **Severity**: SEV1 | SEV2 | SEV3
- **Owner**: service owner on call
- **Expected time to mitigate**: e.g., "10 minutes"

## Impact

Who or what is affected? What is the customer-visible symptom? Is there data loss risk?

## First checks (in order)

1. ALB target health — any unhealthy targets?
2. ECS service — desired vs running task count
3. Recent deployments — anything in the last 30 minutes?
4. SQS queue depth and DLQ depth
5. RDS CPU and connection count
6. Relevant CloudWatch Logs Insights query (paste query here)

## Triage tree

```
Is the symptom <X>?
├── Yes → likely cause A, go to Mitigation A
└── No  → is the symptom <Y>?
          ├── Yes → likely cause B, go to Mitigation B
          └── No  → escalate
```

## Mitigation A

Step-by-step. Include exact CLI commands or console clicks. Mark any destructive action with ⚠️.

## Mitigation B

Step-by-step.

## Recovery verification

How to confirm the system is healthy again. Which dashboard panels or queries should return to green, and within what time window.

## Follow-up

- File an incident ticket
- Update this runbook if any step was wrong or missing
- Consider whether this condition should have been auto-mitigated
