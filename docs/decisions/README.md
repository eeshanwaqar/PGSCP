# Architecture Decision Records

Short, dated records of non-obvious architectural choices and the reasoning behind them. Format follows [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

| # | Title | Status |
|---|---|---|
| [0000](0000-template.md) | Template | — |
| [0001](0001-ecs-fargate-over-eks.md) | Use ECS Fargate instead of EKS | Accepted |
| [0002](0002-sqs-over-kafka.md) | Use SQS + DLQ instead of Kafka/MSK | Accepted |
| [0003](0003-terraform-over-cloudformation.md) | Use Terraform instead of CloudFormation | Accepted |
| [0004](0004-sqs-vs-kinesis-flink.md) | Use SQS, not Kinesis or Flink, for the event pipeline | Accepted |

## When to write an ADR

- The decision is non-obvious or has meaningful tradeoffs.
- Reversing it later would be expensive.
- A future maintainer (or interviewer) would reasonably ask "why did you do it this way?"

Do not write ADRs for things that are idiomatic, self-evident from the code, or pure style choices.
