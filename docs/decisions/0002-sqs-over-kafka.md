# ADR-0002: Use SQS + DLQ instead of Kafka/MSK

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Project owner

## Context

PGSCP decouples event ingestion from event processing with a durable buffer between the API and the worker. This buffer needs to:

1. Absorb traffic spikes so the API returns `202` quickly even when the worker is slow.
2. Isolate the API from worker failures — a crashed worker must not take down ingestion.
3. Retry transient failures automatically.
4. Quarantine poison messages so they don't loop forever.
5. Allow the worker to scale independently from the API.

The realistic AWS options are:

- **SQS** — fully managed pull-based queue. At-least-once delivery for the standard tier, FIFO available. Native dead-letter queue (DLQ) support with redrive policies. Effectively zero operational burden.
- **Amazon MSK** (managed Kafka) — event streaming log. Multi-consumer replay, partitioned ordering, long retention. Significantly more operational complexity even when managed.
- **Kinesis Data Streams** — managed streaming, simpler than Kafka, shard-based.

## Decision

Use **SQS with a dead-letter queue and a `maxReceiveCount=5` redrive policy**.

Idempotency is enforced at the application layer (Postgres unique constraint on `idempotency_key`) since SQS standard queues are at-least-once. The worker uses long polling (`WaitTimeSeconds=20`) to reduce empty-receive cost. Visibility timeout is set above expected max processing time.

## Consequences

### Positive
- Zero infrastructure to manage — no brokers, no ZooKeeper/KRaft, no partition management.
- DLQ + redrive is first-class and matches the "quarantine poison messages" story perfectly.
- At-least-once semantics force the team to get idempotency right in the application layer, which is the correct place for it regardless of the underlying bus.
- Cheap: effectively free at this project's volume.
- One less thing to explain and defend in an interview — the attention stays on IAM, networking, and observability.

### Negative
- No message replay. Once a message is acknowledged, it's gone. If we ever need to reprocess historical events to fix a bug, we must reconstruct them from the raw-event S3 archive. This is acceptable here because we already persist the raw payload to S3 before enqueueing.
- No multi-consumer fan-out from a single message stream. Not needed in this architecture — there's exactly one worker service type.
- No strict ordering across partitions. Not needed — events are independent per `device_id` and the rule engine doesn't assume ordering.

### Neutral / follow-ups
- If the platform ever needs replay, multiple independent consumers, or strict per-key ordering at high fan-out, revisit with MSK or Kinesis.
- The S3 raw-event archive is the reason we can get away without replay. Keep that invariant documented and enforced.

## Alternatives considered

### MSK (managed Kafka)
Rejected. Significant operational surface (partition management, consumer group lag monitoring, broker scaling, upgrade coordination) even in the managed flavor. Multi-consumer replay is its killer feature and we don't need it. The "interview-scope" signal of using Kafka is negative here — it would read as over-engineering for a two-service system.

### Kinesis Data Streams
Rejected for similar reasons to Kafka plus one more: shard management is its own little operational story, and the per-shard pricing penalizes low-traffic workloads. SQS is both simpler and cheaper for this shape.

### Synchronous processing (no queue)
Rejected. The whole point of this architecture is to demonstrate failure isolation and spike absorption between ingestion and processing. Removing the queue would also remove the single most defensible reliability talking point in the interview narrative.

### SQS FIFO
Rejected as the default. FIFO gives broker-level deduplication and strict ordering, but at lower throughput and higher cost. We don't need strict ordering, and application-level idempotency is strictly stronger than broker-level dedup (it catches retries from *any* source, not just the queue). Worth revisiting if duplicate-detection complexity becomes painful.
