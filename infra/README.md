# infra

Terraform for PGSCP. Organized as one-time **bootstrap**, reusable **modules**, and per-environment **roots**.

```
infra/
  bootstrap/          # one-time: tfstate bucket + KMS + GitHub OIDC role
  modules/
    network/          # VPC, subnets (public / private-app / private-data), NAT, SGs
    vpc_endpoints/    # S3 gateway + ECR/Secrets/Logs/SQS/Bedrock interface endpoints
    s3/               # raw events bucket, logs bucket, app KMS key
    iam/              # task execution + per-service task roles
    secrets/          # HMAC key (random), Slack webhook URL, PagerDuty routing key
    sqs/              # generic main queue + DLQ + redrive (instantiated per logical queue)
    rds/              # Postgres 16 — private data subnets, KMS, RDS-managed master password
    # Phase 4+ will add: ecr/ alb/ cloudfront/ ecs_service/ cloudwatch/ cloudtrail/
  envs/
    dev/              # wired against dev AWS account
    prod/             # placeholder; mirrors dev with stricter guards (later)
```

## Phase status

Implemented so far:

- **Phase 2** — bootstrap + network + vpc_endpoints + s3 + iam.
- **Phase 3** — secrets + sqs (events + investigations) + rds. IAM module rewired with real ARNs.

Phases 4–7 are planned in [docs/plan.md](../docs/plan.md) and layer on top of this foundation without rewriting it.

## First-time apply

1. **Bootstrap** (one-time, uses local state):

   ```bash
   cd infra/bootstrap
   terraform init
   terraform apply \
     -var="state_bucket_name=pgscp-tfstate-<account-id>" \
     -var="github_repository=<owner>/<repo>"
   ```

   Capture the `state_bucket_name` and `state_kms_key_arn` outputs.

2. **Dev environment**:

   ```bash
   cd infra/envs/dev
   cp terraform.tfvars.example terraform.tfvars
   # edit terraform.tfvars — set globally-unique bucket names

   terraform init \
     -backend-config="bucket=<state-bucket-name>" \
     -backend-config="kms_key_id=<state-kms-key-arn>"
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

## Design decisions

- **Terraform over CloudFormation** — ADR-0003 (pending). Honest framing: CFN experience is on the CV from NETSOL; Terraform is the current industry default and the skill the market is asking for.
- **One KMS key per scope, not one per resource** — `tfstate` key for state, `app` key for raw events + secrets. Rotation enabled on both. Cheaper and the security boundary matches the data lifecycle.
- **SG-to-SG references, no CIDRs** — the only exception is the ALB's public HTTPS rule. Every internal hop is `api-sg → rds-sg`, not `10.0.0.0/16 → rds-sg`.
- **VPC endpoints in Phase 2, not deferred** — they save NAT data-processing charges immediately and the IAM surface they require (`vpc:*Endpoint`) is simpler to defend in an audit than the alternative of "we meant to add them later".
- **NAT count is a variable** — 1 in dev (cost), 2 in prod (HA). Single knob, same module, zero drift between envs.
- **Data subnets have no egress** — no NAT route from `private_data_rt`. RDS lives there and has no business talking to the internet. VPC endpoints cover any AWS API traffic RDS Proxy or Secrets rotation would need.
- **Conditional IAM statements** — every role has `dynamic "statement"` blocks gated on Phase-3/6 variable values. Phase 3 now populates SQS and secret ARNs; log-group ARNs remain empty until Phase 6. This avoids an intermediate state where the role exists but points at a non-existent resource ARN.
- **RDS-managed master password** — the `rds` module sets `manage_master_user_password = true` so AWS generates and rotates the master credential. Its Secrets Manager ARN is threaded through to the IAM module's `secret_arns` list, so the task execution role can inject it into the container env without a rotation Lambda to maintain.
- **One SQS module, multiple instances** — the `sqs` module is generic (queue name + KMS key + timeouts). The dev env calls it twice: `sqs_events` (60s visibility) and `sqs_investigations` (180s visibility for agent runs). Same module, same guarantees, different tunings.

## Destroy order (dev)

```bash
cd infra/envs/dev && terraform destroy
# then, if you also want to remove the bootstrap:
cd ../../bootstrap
aws s3 rm s3://<state-bucket-name> --recursive
terraform destroy   # prevent_destroy on the state bucket will block until emptied
```

## Cost (rough, dev idle)

- VPC (free) + 1 NAT gateway (~$33/mo fixed + data)
- Interface endpoints: 6 endpoints × ~$7/mo each = ~$42/mo (offset by avoided NAT data processing for ECR/Secrets/Logs/SQS/Bedrock)
- S3: negligible at dev volume
- KMS: 2 CMKs × $1/mo = $2/mo
- SQS: negligible at dev volume (two queues, long-polling)
- Secrets Manager: 3 secrets × $0.40/mo = ~$1/mo (RDS-managed master secret is free)
- RDS `db.t4g.micro` Multi-AZ off, 20 GB gp3: ~$15/mo when running; ~$2/mo when stopped (storage only)

Dev idle with RDS stopped between sessions: ~$80/mo. Full uptime: ~$95/mo. ECS + ALB arrive in Phase 4.

## Verification

After `terraform apply` in `envs/dev/`, verify least-privilege wiring:

```bash
# All subnets created
aws ec2 describe-subnets --filters "Name=vpc-id,Values=$(terraform output -raw vpc_id)" \
  --query 'Subnets[].{AZ:AvailabilityZone,Cidr:CidrBlock,Tier:Tags[?Key==`Tier`]|[0].Value}'

# Raw bucket blocks public access
aws s3api get-public-access-block --bucket "$(terraform output -raw raw_bucket_name)"

# API task role cannot read unrelated S3 buckets
aws iam simulate-principal-policy \
  --policy-source-arn "$(terraform output -raw api_task_role_arn)" \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::some-other-bucket/key
# expected: implicitDeny
```
