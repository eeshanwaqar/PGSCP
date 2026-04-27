# ADR-0003: Use Terraform instead of CloudFormation

- **Status**: Accepted
- **Date**: 2026-04-27
- **Deciders**: Project owner

## Context

PGSCP needs an Infrastructure-as-Code tool to define every AWS resource the
platform uses: VPC + subnets, RDS, S3, SQS, IAM, KMS, ECR, ECS Fargate
services, ALB, CloudFront, CloudWatch. The two realistic options are:

- **Terraform** (with the `hashicorp/aws` provider)
- **AWS CloudFormation** (or its higher-level CDK wrapper)

Personal note: I have prior production experience with CloudFormation at a
previous role. This ADR is not about CFN being a bad tool — it is about what
the right default is **for this project, in 2026, given who I am building it
for**.

The audience for this repo is hiring teams looking for AI/ML platform engineers.
Terraform is the de-facto industry default for that audience: every job posting
in the space lists Terraform; CloudFormation is rarely listed by name except
inside AWS-only shops.

## Decision

Use **Terraform** as the IaC layer for every PGSCP resource.

Terraform 1.9+ as the binary. State stored in S3 with KMS encryption + native
S3 lockfile (no DynamoDB lock table required from Terraform 1.10+, and 1.9 also
supports `use_lockfile`). Bootstrap module is the one piece that uses local
state — it bootstraps the very bucket everyone else reads from.

Modules are structured as one purpose per directory (`network`, `iam`, `s3`,
`secrets`, `sqs`, `rds`, `ecr`, `ecs_cluster`, `ecs_service`, `alb`,
`vpc_endpoints`). Per-environment roots (`envs/dev/`, `envs/dev-shared/`,
`envs/prod/`) compose modules but never contain inline resource blocks beyond
the root-level data sources.

## Consequences

### Positive
- Matches what every prospective employer in the AI/ML platform space expects.
- HCL is materially more concise than CloudFormation YAML/JSON for nested
  resources, conditional logic, and `for_each` patterns. The same VPC + 3-tier
  subnets + NAT in CFN is roughly 2× the line count.
- The Terraform Registry has first-party + community modules for everything
  exotic. CloudFormation registry coverage is narrower outside AWS-managed
  resource types.
- `terraform plan` produces a far more readable diff than CloudFormation
  ChangeSets. PR-attached plans are first-class in our CI workflow
  (`.github/workflows/terraform-plan.yml`).
- Drift detection (`terraform plan` against current state) is workable and
  routine. CloudFormation's `detect-drift` exists but is awkward to operationalize.
- Provider-level abstractions cleanly span account + region boundaries when
  multi-region eventually matters; CloudFormation requires StackSets for the
  same.
- I retain my prior CloudFormation experience. Knowing both is a strictly
  larger skillset than knowing one.

### Negative
- Terraform state is a critical artifact we now own. Lose it and recovery
  requires `terraform import` of every resource. Mitigated by versioned,
  KMS-encrypted, public-blocked S3 storage with `prevent_destroy` on the bucket.
- HCL is its own dialect. CloudFormation YAML is at least vanilla YAML and
  every developer can read it.
- HashiCorp's BUSL relicensing in 2023 introduced licensing risk for vendors
  shipping Terraform-derived products. Not relevant for application use, but
  worth noting. OpenTofu is a drop-in fork if it ever becomes relevant.
- CloudFormation has tighter native AWS integration in places (Stacks visible
  in the AWS console, drift detection events in EventBridge, AWS-managed
  rollback for stack failures). Terraform's `deletion_protection` /
  `prevent_destroy` lifecycle rules cover most of the same ground but
  out-of-band.

### Neutral / follow-ups
- Revisit if PGSCP joins an organization with an existing AWS-CFN platform
  team. The right answer there is "use what they use", not "import everything
  into Terraform".
- If we add multi-account or multi-region complexity, we'd evaluate
  Terragrunt or AWS Control Tower-style account vending. Not needed at this
  scope.
- CDK (TypeScript over CloudFormation) is a credible third option for
  TypeScript-heavy teams. We did not choose it because the rest of the project
  is Python — adding a TypeScript build for infra alone would be friction with
  no offsetting gain.

## Alternatives considered

### CloudFormation (raw YAML)
Rejected. Verbose for the size of the surface (~12 modules, dozens of
resources), weaker module ecosystem for the niche bits (e.g. clean OIDC + GitHub
trust policy templates), and outside the audience expectation for this kind of
project.

### AWS CDK (TypeScript)
Rejected. Strictly higher-level than CloudFormation and the loops/conditionals
are a strict improvement, but introduces a TypeScript build into an otherwise
Python project. Worth re-evaluating if the team is already TypeScript-native.

### Pulumi
Rejected. Same conceptual model as CDK with multi-language support; would have
been a defensible choice, but Pulumi adds a paid SaaS state-backend default
(`app.pulumi.com`) that I'd want to opt out of, and the audience expectation is
Terraform.

### OpenTofu
Considered seriously after HashiCorp's BUSL move. We stayed on Terraform
because the immediate compatibility surface is identical and the licensing
concern doesn't apply to platform application use. Easy to switch later if
warranted — every `.tf` file in this repo is OpenTofu-compatible.

---

**Footnote on personal background:** I have shipped CloudFormation in
production at a previous role. The choice here is not "Terraform good, CFN
bad" — it is "this is the language the audience for this repo speaks, and the
ergonomic differences favor Terraform for a 12-module, multi-environment
project of this shape."
