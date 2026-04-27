# ADR-0004: Use SQS, not Kinesis or Flink, for the inference event pipeline

- **Status**: Accepted
- **Date**: 2026-04-27
- **Deciders**: Project owner

## Context

PGSCP has two queueing needs:

1. **Events queue** — the API enqueues each ingested `InferenceRecord` for the
   worker to evaluate. One producer (API), one logical consumer (worker).
2. **Investigations queue** — the worker enqueues high-severity alerts for
   the LangGraph investigator to process. One producer (worker), one logical
   consumer (investigator).

Both flows are point-to-point, durable async work-queues. Neither needs
multi-consumer fan-out, time-windowed analytics, ordered partitioning by key,
or replay beyond what the S3 raw-events archive already provides (we keep the
raw payload in S3 for 180 days; replay is "re-enqueue from S3" not
"rewind a stream").

Personal note: I have prior production experience with Amazon Kinesis and
Apache Flink at a previous role, where they were the right tools for a
multi-consumer, windowed-analytics pipeline. This ADR is about why **PGSCP
specifically** doesn't need either.

The realistic options on AWS:

- **SQS** (Simple Queue Service) — managed work-queue. Pull-based consumer,
  visibility timeout, DLQ, FIFO option, AWS-managed encryption, pay per
  request.
- **Kinesis Data Streams** — managed log/stream. Push-based consumers via
  KCL or Lambda, ordering per partition key, 24h–365d retention, fan-out
  to N consumers from the same stream.
- **MSK / self-hosted Kafka** — same shape as Kinesis with a richer ecosystem
  but heavier ops burden.
- **Apache Flink (KDA / Flink-on-K8s)** — stream-processing engine, layered
  *on top of* a stream source like Kinesis or Kafka.

## Decision

Use **SQS** for both queues. KMS-encrypted, with DLQs and `maxReceiveCount=5`.
Different visibility timeouts per queue (60s for events, 180s for
investigations — the LangGraph agent runs longer than rule evaluation).

## Consequences

### Positive
- Matches the workload exactly: durable async buffering between two services.
  No conceptual mismatch.
- Trivially cheap at this scale. Both queues together cost pennies per month
  in dev; production cost is bounded by request volume, not by partition shards.
- Pull-based consumers compose naturally with ECS Fargate auto-scaling on
  queue depth — `ApproximateNumberOfMessagesVisible` is a first-class CloudWatch
  metric you can drive autoscaling from.
- Idempotency story is clean: SQS is at-least-once, we dedupe on
  `idempotency_key` via a Postgres unique constraint. Standard pattern.
- DLQ + redrive policy is one Terraform block. Operationally trivial to
  redrive after fixing a bug.
- Visibility timeout maps cleanly to "how long do I have to process this
  message" — easier reasoning than Kinesis's checkpoint-and-shard model for our
  shape.
- KMS encryption at rest is one Terraform attribute. (Caused one real-world
  bug — the worker's IAM role needed `kms:GenerateDataKey` to send to the
  encrypted investigations queue. Fixed in commit history. The bug is exactly
  the kind of artifact a security-conscious reviewer would want to see.)
- Lower cognitive load for the next engineer reading the code. SQS is the
  default-AWS primitive everyone knows.

### Negative
- No multi-consumer fan-out. If we ever want a second analytics consumer
  reading the same events without competing with the worker, we can't do it
  with SQS alone — we'd need SNS-fan-out-to-multiple-SQS, or switch to Kinesis.
- No long replay window. SQS retention is configurable up to 14 days, but it's
  a queue, not a log. We mitigate by archiving every raw event to S3
  (`raw/model=<m>/dt=<d>/<event_id>.json`) — replay = re-enqueue from S3.
- No native ordering across the queue. We don't need it (each event is
  independent), but if a future feature required strict per-model ordering
  we'd reach for SQS FIFO at minimum, possibly Kinesis with model-as-partition-key.

### Neutral / follow-ups
- The S3 raw-events archive is the de-facto replay log. If a rule changes and
  we want to re-evaluate the last 30 days, we walk the S3 partitions and
  re-enqueue. This is documented as the replay strategy in
  [`docs/blueprints/pgscp.md`](../blueprints/pgscp.md).
- If PGSCP ever adds a real-time analytics pane (e.g. per-minute rule fire
  rates by region, or cross-event correlation windows), Kinesis or Kinesis
  Firehose into Athena would be the right addition — alongside SQS, not
  instead of it.
- Flink would only become relevant if we needed stateful stream operators
  (windowed joins, sessionization, complex event processing). PGSCP rules
  are stateless per-event with a small Postgres-backed lookback. No fit.

## Alternatives considered

### Kinesis Data Streams
Rejected for this workload. Strengths irrelevant here:
- *Multi-consumer fan-out* — we have one consumer per queue.
- *Long replay window* — already covered by S3 raw archive.
- *Ordering per partition key* — not required.

Weaknesses that matter:
- Shard provisioning + on-demand pricing model is overkill for our throughput.
- KCL adds a checkpoint table (DynamoDB) that becomes another moving part.
- The IAM model is more complex (stream + shard-iterator perms vs SQS's clean
  receive/delete/sendMessage trio).

### MSK / self-managed Kafka
Rejected. All the downsides of Kinesis plus the ops burden of running brokers,
ZooKeeper-equivalent, partition rebalancing. PGSCP's "one engineer owns it"
narrative collapses under this choice.

### Apache Flink (KDA or Flink-on-K8s)
Rejected. Flink is a stream-processing engine that runs *on top of* a stream
source. PGSCP's rule engine is per-event stateless logic with a tiny
Postgres-backed lookback — pure pull-and-process. There is no streaming
operator (windowed aggregation, sessionization, join across streams) that
would justify a Flink job. Bringing in Flink would be solution-looking-for-a-
problem.

### EventBridge
Considered briefly. EventBridge is great for cross-service routing with
filtering rules, but the worker doesn't need EventBridge's schema/registry/rule
features — it needs a plain durable buffer with at-least-once delivery and a
DLQ. SQS is the simpler match.

---

**Footnote on personal background:** I built and operated Kinesis +
Flink-on-K8s pipelines at Graph8 for a multi-consumer, windowed-analytics
workload — it was the right tool there because the data shape was a
high-throughput log being consumed by N independent analytics jobs with
windowed aggregations. The shape of PGSCP's pipeline is different: one
producer, one consumer per logical queue, no analytics, no replay beyond what
S3 already provides. **Choosing the simpler primitive when the workload
allows it is itself a senior-engineer signal.**
