# Few-shot investigations

Each example below is a real (anonymized) alert → investigation pair. They are appended to the system prompt as exemplars. Keep them short.

## Example 1 — LatencyBreach → upstream provider queueing

Alert: `LatencyBreach` on `gpt-4o-mini`, latency 2840ms, threshold 1500ms.
Evidence: 4 similar alerts in the last 10 minutes for the same model; recent `recent_deployments` shows no client-side deploys in the last 24h; `inference_record` shows prompt_tokens=600 (unchanged from baseline).

```json
{
  "root_cause_label": "upstream_provider_queueing",
  "root_cause": "Provider-side queueing on gpt-4o-mini — four alerts in 10 minutes with no client-side changes, stable prompt size, and a clustered latency distribution consistent with queueing rather than a regression.",
  "confidence": 0.86,
  "remediation": [
    "Check OpenAI status page for gpt-4o-mini incidents",
    "Temporarily route critical traffic to gpt-4o as fallback",
    "Tighten client-side p95 timeout to fail fast and free workers"
  ],
  "hypotheses_considered": [
    {"label": "upstream_provider_queueing", "rationale": "Alert cluster + stable prompt size", "confidence": 0.86, "evidence_ids": ["recent_alerts", "inference_record"]},
    {"label": "network_path_degradation", "rationale": "Possible but no supporting log evidence", "confidence": 0.2, "evidence_ids": []}
  ],
  "evidence_citations": ["alert", "inference_record", "recent_alerts", "deployments"]
}
```

## Example 2 — PiiLeak → weakened redaction

Alert: `PiiLeak` on `claude-sonnet-4-5`, completion contained two emails.
Evidence: `inference_record.completion` shows raw email addresses verbatim; `recent_deployments` shows an api deploy 2 hours before the alert; no prior `PiiLeak` alerts in the 24h before the deploy.

```json
{
  "root_cause_label": "redaction_regression_in_deploy",
  "root_cause": "The most recent API deploy (2 hours before the alert) removed or weakened the PII redaction step — zero PiiLeak alerts in the 24h prior and two verbatim emails in the completion after the deploy.",
  "confidence": 0.91,
  "remediation": [
    "Roll back the most recent api service deployment immediately",
    "Purge the offending completion from the raw events bucket",
    "Add a redaction-coverage assertion to the api test suite"
  ],
  "hypotheses_considered": [
    {"label": "redaction_regression_in_deploy", "rationale": "Temporal correlation with deploy + clean prior window", "confidence": 0.91, "evidence_ids": ["deployments", "recent_alerts", "inference_record"]}
  ],
  "evidence_citations": ["alert", "inference_record", "recent_alerts", "deployments"]
}
```
