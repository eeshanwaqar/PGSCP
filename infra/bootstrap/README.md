# infra/bootstrap

One-time Terraform root that provisions the dependencies every other root needs before it can run:

- KMS key + alias (`alias/pgscp-tfstate`) — encrypts remote state at rest.
- S3 bucket — holds Terraform remote state (versioned, encrypted, public access blocked, `prevent_destroy`).
- IAM OpenID Connect provider for GitHub Actions.
- IAM role (`pgscp-github-oidc`) — the role CI assumes via OIDC; policy-bound to the configured repo + refs.

This root intentionally uses **local state** (no `backend` block) because it is bootstrapping the very bucket used as the backend. After a successful first apply, commit the generated `terraform.tfstate` to a private location outside the repo (e.g. an encrypted password manager) — it is small and rarely changes.

## Apply

```bash
cd infra/bootstrap
terraform init
terraform apply \
  -var="state_bucket_name=pgscp-tfstate-<your-account-id>" \
  -var="github_repository=<owner>/<repo>"
```

The bucket name must be globally unique. A common convention: `pgscp-tfstate-<account-id>`.

## Outputs consumed by other roots

- `state_bucket_name` → `infra/envs/{dev,prod}/backend.tf`
- `state_kms_key_arn` → `infra/envs/{dev,prod}/backend.tf` (`kms_key_id`)
- `github_oidc_role_arn` → `.github/workflows/*.yml` (`role-to-assume`)

## Destroy

Destroying the bootstrap root will fail while the state bucket still contains objects from other envs. Tear down `dev` and `prod` roots first, then manually empty the bucket, then `terraform destroy`. The `prevent_destroy` lifecycle rule exists on the bucket specifically to force this order.
