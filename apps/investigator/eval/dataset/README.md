# Eval dataset

`golden.jsonl` is the hand-labelled golden set the investigator graph is evaluated against.

## Format

Each line is a JSON object:

```json
{
  "id": "<case-id>",
  "seed": {
    "alert_id": <int>,
    "event_id": "<str>",
    "model": "<str>",
    "rule": "<RuleName>",
    "severity": "warn|critical|info",
    "alert_message": "<str>",
    "alert_evidence": {},
    "alert_created_at": "<iso8601>",
    "evidence": [{"id": "<str>", "source": "<enum>", "summary": "<str>", "data": {}}]
  },
  "label": {
    "root_cause_label": "<snake_case>",
    "evidence_ids": ["<id>", "..."],
    "min_tool_calls": <int>
  }
}
```

`seed` is a self-contained `InvestigationState` — the eval runner injects it directly into the graph, skipping DB/S3/CloudWatch tools. This makes the harness a pure function of the model + prompt, which is what we want for regression detection.

## Why the seed includes evidence

The real graph fetches evidence from tools (DB/S3/CloudWatch/ECS). In eval we pre-bake evidence into each case so:

1. Runs are deterministic — no tool flakiness, no time-dependent queries.
2. `evidence_precision` is computable — we know exactly which ids the model *should* cite.
3. Prompt or model changes are the only thing that can move the metrics — which is exactly what the CI gate is trying to detect.

## Baseline vs real

The default `scripted` backend returns hand-written responses keyed by rule, so running it against this dataset reports near-100% accuracy. That's a baseline sanity check, not a real measurement — it proves the pipeline works end-to-end.

The real numbers come from running `--backend bedrock` or `--backend openai`. The "tricky" cases (suffix `-tricky`) are designed to *fail* the default priors so a real LLM has to reason from evidence to get them right. Those are the cases that make the metric meaningful.

## Growing the dataset

1. Human reviews an investigation via the feedback endpoint.
2. If they mark it `correct=false`, the service stages a file under `/tmp/pgscp/regressions/`.
3. A GitHub Action picks up staged files and opens a PR appending them to `regressions.jsonl` (sister file, same format).
4. Review the PR, add proper labels, merge.

`regressions.jsonl` is loaded by the same runner when `--include-regressions` is passed. CI gates on the combined accuracy to prevent the agent from fixing the original cases at the cost of regressions.

## Target growth

- Phase 8a: 10 cases (this file).
- Phase 8b: 50 cases (hand-grown from a week of local docker-compose runs).
- Phase 9 (post-deployment): 100+ cases, 50% from real production feedback.
