# ADR-0001: Use ECS Fargate instead of EKS

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Project owner

## Context

PGSCP needs a container runtime to host the API service and the worker service. Both are stateless Python services packaged as Docker images. They need to scale independently, retrieve secrets at runtime, assume IAM roles without static credentials, and deploy through CI/CD with safe rollback.

The two realistic options on AWS are:

- **ECS Fargate** — AWS-native container orchestration with serverless compute (no EC2 nodes to patch, scale, or autoscale).
- **Amazon EKS** — managed Kubernetes. More portable across clouds, larger ecosystem, but also a significant platform surface to own (cluster add-ons, upgrades, RBAC, CNI, ingress controllers, observability plumbing).

This project is deliberately scoped as what **one engineer can own end-to-end**. The goal is to demonstrate infrastructure ownership, security posture, deployment safety, and operational discipline — not to demonstrate Kubernetes depth.

The workload is simple: two long-running stateless services behind an ALB, consuming from SQS, talking to RDS and an external API. There is no multi-tenancy, no batch scheduling, no need for custom controllers, no portability requirement across clouds.

## Decision

Use **ECS Fargate** for both the API and worker services.

Task roles and execution roles will be used per the AWS-recommended split. Deployments will use the ECS deployment circuit breaker with automatic rollback. Service autoscaling will be wired to CPU utilization for the API and to SQS queue depth for the worker.

## Consequences

### Positive
- Zero node-level operational burden — no EC2 patching, AMI management, or cluster add-on upgrades.
- Clean IAM story: task execution role vs task role is a small, defensible surface.
- Deployment circuit breaker and 1-click rollback are first-class ECS features.
- Fits the "one engineer owns the platform" narrative cleanly.
- Lower baseline cost than a permanently-running EKS control plane (~$73/month for EKS control plane alone).
- Fast time-to-first-deploy — we can be in AWS dev by Week C of the plan.

### Negative
- Less portable. If the project ever needs to move off AWS or onto a Kubernetes-first shop, we'd have to rewrite task definitions as manifests.
- Smaller ecosystem of off-the-shelf tooling compared to Kubernetes (helm charts, operators, service meshes).
- Less impressive on a CV for roles specifically hiring Kubernetes operators. Mitigated by being explicit in the interview narrative: "I chose ECS Fargate because the workload didn't justify Kubernetes — and knowing *when not to* reach for K8s is itself a signal."

### Neutral / follow-ups
- Revisit if the platform grows to >10 services, introduces batch/cron workloads that would benefit from Kubernetes' scheduling primitives, or joins a company with an existing K8s platform team.
- If we need pod-level scheduling features, GPU workloads, or stateful sets, EKS becomes the right answer.

## Alternatives considered

### EKS (managed Kubernetes)
Rejected. Significant platform surface to own for no functional gain on this workload. The EKS control plane has a non-trivial baseline cost. Kubernetes expertise would add weeks to the build without making the system more correct, more secure, or more reliable for this problem shape.

### ECS on EC2
Rejected. Reintroduces the very node-management burden Fargate removes. Only justifiable if we hit a Fargate pricing ceiling or need custom kernel/AMI features — neither applies here.

### AWS App Runner
Rejected. Simpler than Fargate but too opinionated — no first-class VPC integration with private subnets the way Fargate has, no clean split between API and worker service topologies, and the IAM / observability story is weaker. It would undercut the very security and networking narrative this project exists to demonstrate.
