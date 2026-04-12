# Cloud Engineer Project Blueprint

> Source: initial project brief. Preserved verbatim for reference. Authoritative design is [pgscp.md](pgscp.md); executable plan is [../plan.md](../plan.md).

## Project Title

Production-Grade Event Processing and Alerting Platform on AWS

## Purpose

Build a production-style cloud platform that proves end-to-end ownership of infrastructure, security, CI/CD, networking, observability, reliability, and cost-conscious design.

This project is specifically designed to prepare for a Cloud Engineer role focused on:

- AWS ownership
- Terraform and Infrastructure as Code
- CI/CD and deployment safety
- IAM, secrets, encryption, and auditability
- monitoring, alerting, and postmortems
- external system integrations
- startup-style operational ownership

## 1. Project Summary

The application is a real-time event ingestion, processing, and alerting platform.

Users or partner systems send events to an API. The API accepts and validates requests, stores audit data, and pushes processing jobs onto a queue. Worker services consume the queue, apply business rules or anomaly checks, store alert outcomes, and optionally send alerts to an external partner API.

The platform must be secure, observable, reproducible, and production-ready.

## 2. What This Project Demonstrates

### Infrastructure Ownership
- designing the AWS architecture
- setting up networking correctly
- defining infrastructure in Terraform
- managing environments consistently

### Reliability Engineering
- decoupling ingestion from processing
- handling spikes and retries safely
- defining health checks and rollback paths
- creating useful alerts and dashboards

### Security Engineering
- least-privilege IAM
- secure secrets handling
- encryption at rest and in transit
- auditability and change tracking

### Deployment Engineering
- Dockerized services
- CI/CD with safe deployments
- environment-specific configs
- rollback strategy

### External Integration Discipline
- partner API integration with retry and timeout handling
- outbound security considerations
- observability for cross-system failures

## 3. Functional Requirements

### API Service

Expose endpoints such as:
- `POST /events` to receive event payloads
- `GET /alerts` to retrieve generated alerts
- `GET /health` for liveness checks
- `GET /ready` for readiness checks
- `GET /metrics` for observability

### Event Processing
- validate inbound events
- enqueue valid events for async processing
- reject malformed requests cleanly
- preserve an audit trail

### Worker Service
- consume events from queue
- process business rules or anomaly logic
- create alerts when thresholds are exceeded
- store results in the database
- call external partner webhook/API when needed
- retry transient failures

### Alerting Rules

Examples:
- temperature greater than threshold
- repeated failures within a time window
- sudden change in event value compared to rolling average
- missing heartbeat from a device/service

### External Partner Integration
- secure outbound API call
- idempotency support if possible
- timeout and retry logic
- dead-letter or failure path if partner API is unavailable

## 4. Non-Functional Requirements

### Security
- all secrets stored outside code
- least-privilege IAM roles
- TLS for inbound traffic
- database not publicly accessible
- encrypted storage

### Reliability
- API remains responsive even when downstream systems slow down
- worker failures do not take down ingestion layer
- retries do not cause duplicate processing side effects
- deployment failures can be rolled back

### Observability
- request latency metrics
- queue depth metrics
- worker error metrics
- external integration failure metrics
- dashboard for system health
- alerts tied to actionable conditions

### Cost Awareness
- no unnecessary always-on components
- autoscaling where justified
- right-sized compute
- minimal complexity for current scale

## 5. Architecture

### Recommended AWS Services

- **CloudFront** for edge distribution and optional TLS/front-door hardening
- **Application Load Balancer** for routing HTTP traffic
- **ECS Fargate** for API and worker services
- **ECR** for container images
- **SQS** for async decoupling
- **RDS PostgreSQL** for transactional storage
- **S3** for archives, reports, and optional Terraform backend state
- **Secrets Manager** for secrets
- **CloudWatch** for metrics, logs, alarms, and dashboards
- **CloudTrail** for auditability
- **VPC** with public and private subnets
- **NAT Gateway** for private subnet outbound internet access

### Network Layout
- 1 VPC
- 2 Availability Zones
- public subnets for ALB and NAT
- private application subnets for ECS services
- private data subnets for RDS

### Traffic Flow

1. Client sends request to CloudFront or ALB
2. ALB forwards request to ECS API service
3. API validates request
4. API writes event metadata / audit record
5. API pushes message to SQS
6. Worker consumes message
7. Worker processes rules and creates alerts
8. Worker stores results in RDS and archives raw/processed data to S3 if needed
9. Worker sends selected alerts to external partner API
10. Logs and metrics are emitted to CloudWatch throughout

## 6. Core Architecture Decisions and Rationale

**Why ECS Fargate instead of EKS** — Use ECS Fargate first because the goal is to show infrastructure ownership, deployment discipline, networking, security, and observability without introducing extra Kubernetes operational overhead.

**Why SQS between API and Worker** — SQS decouples ingestion from processing, helps absorb spikes, improves resilience, and allows worker scaling independent of API scaling.

**Why RDS Postgres** — The platform needs consistent transactional state for alerts, audit records, delivery attempts, and system metadata.

**Why S3** — S3 is ideal for low-cost durable storage for archives, artifacts, exports, logs, and deployment-related files.

**Why Private Subnets** — Application services and the database should not be directly accessible from the internet. Only the ALB should be public.

**Why Secrets Manager** — Secrets must not live in code, images, CI variables, or Terraform plaintext outputs.

## 7. Security Model

### IAM Strategy

Create separate IAM roles for:
- ECS task execution
- API service task role
- Worker service task role
- CI/CD deployment role

**API task role permissions**
- send messages to SQS
- read specific secrets from Secrets Manager
- write logs and metrics

**Worker task role permissions**
- read from SQS
- read specific secrets
- access specific S3 buckets or prefixes
- connect to database through app credentials
- write logs and metrics

### Secrets Strategy

Store the following in Secrets Manager:
- database credentials
- external partner API key
- application signing secret
- optional webhook keys

### Encryption Strategy
- HTTPS at the load balancer
- encryption at rest for RDS
- server-side encryption for S3
- encrypted secrets in Secrets Manager

### Auditability
- enable CloudTrail
- structure logs with correlation IDs
- track infrastructure changes in Git
- require CI/CD logs for deployments

### ISO 27001-Style Practices to Reflect
- least privilege
- documented ownership
- documented change management
- reproducible environments
- clear access boundaries
- traceable operational actions

## 8. Terraform Blueprint

### Folder Layout

```
infra/
  environments/
    dev/
    staging/
    prod/
  modules/
    vpc/
    security_groups/
    alb/
    ecr/
    ecs_cluster/
    ecs_service/
    rds/
    s3/
    sqs/
    iam/
    secrets/
    cloudwatch/
    cloudtrail/
```

### Environment Approach

Each environment should:
- reuse modules
- have its own variables and tfvars
- be reproducible independently
- reflect the same architecture pattern with different scale and cost settings

### Terraform Deliverables
- reusable modules
- remote state backend
- separate environment configs
- outputs for service endpoints, resource identifiers, and deployment references

## 9. Application Repo Structure

```
project-root/
  app/
    api/
    worker/
    core/
    models/
    services/
    integrations/
    db/
  tests/
    unit/
    integration/
    smoke/
  infra/
  .github/workflows/
  docker/
  scripts/
  docs/
    architecture/
    runbooks/
    postmortems/
    decisions/
```

### Internal App Modules
- `api/` request handlers and schemas
- `worker/` queue consumer logic
- `core/` config, logging, settings
- `models/` domain models and DTOs
- `services/` business rules and alert generation
- `integrations/` external partner client
- `db/` data access and migrations

## 10. CI/CD Blueprint

### Pipeline Goals
- safe, repeatable deployments
- automated validation before release
- visible audit trail for every deployment

### Suggested GitHub Actions Pipeline

1. Run linting
2. Run unit tests
3. Run integration tests
4. Build Docker image
5. Push image to ECR
6. Run Terraform format and validate
7. Run Terraform plan
8. Deploy to staging
9. Run smoke tests
10. Manual approval for prod
11. Deploy to prod
12. Verify health checks
13. Roll back if deployment is unhealthy

### CI/CD Safety Features
- branch protections
- required checks before merge
- image tagging with commit SHA
- immutable image references in deployments
- separate deploy workflows for staging and prod

## 11. Observability Blueprint

### Logs

Every service should emit structured logs containing:
- timestamp
- service name
- environment
- request ID / correlation ID
- event ID
- alert ID if applicable
- severity level
- error class

### Metrics

Track at minimum:
- API request count
- API latency p50/p95/p99
- API 4xx/5xx rates
- SQS queue depth
- worker processing throughput
- worker failures
- external API latency and failure rate
- ECS CPU and memory utilization
- RDS CPU and connections

### Dashboards

Create dashboards for:
1. API health
2. worker and queue health
3. database health
4. external partner integration health
5. business-level alerts generated per hour/day

### Alarms

Create high-signal alarms for:
- elevated 5xx rates
- sustained high API latency
- queue backlog above threshold
- repeated worker failures
- external integration failure burst
- database connection pressure

## 12. Reliability Blueprint

### Health Checks

Implement:
- liveness check: service process is alive
- readiness check: service is ready to serve traffic

Readiness should include dependency awareness where appropriate.

### Retry Strategy

Use retries only for transient failures:
- external partner API timeouts
- temporary network errors
- queue visibility timeout issues

Avoid blind retries that create duplication.

### Failure Isolation

Design such that:
- API stays available if worker is degraded
- queue absorbs pressure during spikes
- external partner outage does not break ingestion
- failed downstream deliveries can be replayed

### Rollback Strategy
- failed deployment health checks trigger rollback
- previous task definition or image tag remains available
- incidents should result in a documented fix, not just a restart

## 13. Cost Optimization Blueprint

### Cost-Conscious Choices
- use Fargate to avoid managing EC2 nodes initially
- scale worker count based on demand
- keep dev/staging sized smaller than prod
- archive to S3 instead of overusing database storage
- avoid introducing Kafka or EKS until justified

### Cost Optimization Talking Points
- design for demand-based scaling
- choose managed services where operational simplicity reduces hidden cost
- monitor idle resources and overprovisioned components
- balance cost with resilience and operational overhead

## 14. External Integration Design

### Mock Partner System

Create a mock external API service that receives alerts from your platform.

### Integration Requirements
- authentication via API key or signed token
- timeout settings
- retry with exponential backoff
- delivery status tracking
- idempotency support if possible

### Failure Scenarios to Support
- partner returns 500
- partner times out
- invalid credentials
- intermittent network errors

### Observability Requirements
- outbound call latency
- retry counts
- failure reason tracking
- alarm on sustained partner API failure

## 15. Milestone Plan

- **Phase 1: Foundation** — initialize repo, define architecture docs, set up Docker for API and worker, create Terraform skeleton
- **Phase 2: Core Infrastructure** — provision VPC, subnets, route tables, ALB, ECS, ECR, SQS, RDS, S3; deploy initial API and worker
- **Phase 3: Security and Config** — implement IAM roles, store secrets in Secrets Manager, enforce least privilege, enable encryption and logging
- **Phase 4: CI/CD** — add GitHub Actions workflows, automate build/push/deploy, add smoke tests and rollback logic
- **Phase 5: Observability and Reliability** — add structured logging, metrics, CloudWatch dashboards, alarms, readiness/liveness checks
- **Phase 6: External Integration and Incident Simulation** — build mock partner API, integrate outbound alert delivery, simulate partner failures, write incident postmortem

## 16. Incident Scenarios to Simulate

**Scenario A: Queue Backlog Explosion** — Cause worker throughput to lag behind ingestion. Show alarm firing, queue depth rising, mitigation through autoscaling or worker tuning.

**Scenario B: Partner API Outage** — Mock repeated partner failures. Show retries and backoff, ingestion staying healthy, failure tracking and alerting, replay strategy after recovery.

**Scenario C: Bad Deployment** — Deploy a broken version of the API or worker. Show health check failure, rollback process, postmortem notes.

**Scenario D: Overly Broad IAM Policy** — Start with a permissive policy, then tighten it and document the improvement. Useful for interview storytelling.

## 17. Documentation Requirements

- `README.md` — what the system does, architecture summary, how to run locally, how to deploy
- `docs/architecture/overview.md` — architecture diagram, component responsibilities, traffic flow, security boundaries
- `docs/decisions/` — ADRs for ECS vs EKS, SQS vs synchronous processing, RDS vs DynamoDB, Secrets Manager vs environment variables
- `docs/runbooks/` — deployment, rollback, partner API outage, queue backlog, database access issue
- `docs/postmortems/` — at least one real postmortem from a simulated incident

## 18. Interview Defense Narrative

- **Ownership**: "I designed and operated the infrastructure end-to-end, including networking, security, deployments, observability, and failure handling."
- **Security**: "I enforced least privilege, centralized secrets management, private networking, and auditability from the start."
- **Reliability**: "I decoupled request ingestion from processing using SQS to improve resilience and handle spikes safely."
- **External Integrations**: "I treated partner integrations as first-class production risks, with retries, timeout controls, delivery observability, and fallback behavior."
- **Cost Discipline**: "I made service and architecture choices that balanced simplicity, reliability, and cloud cost."

## 19. Success Criteria

The project is successful when:
- infrastructure can be recreated from Terraform reliably
- API and worker are deployed through CI/CD
- services run privately behind a public ALB only
- secrets are not stored in code or plaintext config
- useful dashboards and alarms exist
- external partner failures do not take down ingestion
- at least one production-style incident has been simulated and documented
- every major architecture decision and tradeoff can be explained clearly

## 20. Implementation Order

1. Define repo structure and generate starter files
2. Generate FastAPI API service scaffold
3. Generate worker service scaffold
4. Define event and alert schemas
5. Create Dockerfiles
6. Create Terraform modules incrementally
7. Create GitHub Actions workflows
8. Add structured logging and metrics
9. Add integration client for external partner API
10. Create architecture docs, runbooks, and a postmortem template

## 21. Implementation Constraints

- Prefer simplicity over excessive service sprawl
- Use managed AWS services where they help reduce operational burden
- Keep the project small enough to finish, but deep enough to defend technically
- Every component should exist for a reason that can be explained in an interview

## 22. Final Instruction

Build this as if it were a real startup platform that one engineer is expected to own. Every decision should be explainable in terms of security, reliability, scalability, auditability, and cost.

The output should prioritize:
- correctness
- production-minded defaults
- clean documentation
- realistic Terraform structure
- clear operational reasoning

Do not treat this as a toy app. Treat it as an interview-grade cloud engineering system.
