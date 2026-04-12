# Sample events

Hand-crafted LLM inference records for local development and for the Phase 7 incident simulations. Each file is a single `InferenceRecord` body for `POST /events`.

| File | Purpose | Rule expected to fire |
|---|---|---|
| `happy.json` | Happy path, fully labeled, within thresholds | None |
| `latency-breach.json` | 4.2s latency against a 1.5s threshold | `LatencyBreach` |
| `cost-anomaly.json` | $0.95 single-call cost against a $0.50 threshold | `CostAnomaly` |
| `pii-leak.json` | Completion contains an email and a phone number | `PiiLeak` |
| `accuracy-drift-setup.json` | Single mislabeled record — does not fire on its own but seeds the `AccuracyDrift` rolling window | None (seed) |

## Usage

```bash
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: local-test-1' \
  -d @happy.json
```

## Notes

- `StuckModel`, `AccuracyDrift`, and `MissingHeartbeat` are context-dependent — they fire based on *history* across many records, not on a single record. Reproduce them by replaying the same (or matching) record many times in a row, or by leaving the system idle for > `missing_heartbeat_minutes`.
- `ToxicityHeuristic` is a placeholder keyword matcher by design; don't commit a sample that triggers it (keeps the repo clean).
