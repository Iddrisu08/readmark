# ReadMark — Infrastructure (Terraform)

Provisions a simple, low-cost AWS deployment of the ReadMark backend on a single
EC2 instance running Docker. Intentionally lean — no ECS/RDS/ALB — using the
account's **default VPC**.

## What it creates

| Resource | Purpose |
|---|---|
| EC2 (t3.micro, Amazon Linux 2023) | Runs the app container via Docker |
| Elastic IP | Stable public address |
| Security group | 80/443/8000 open, 22 restricted to `ssh_ingress_cidr` |
| ECR repository | Stores the app image (lifecycle: keep last 10) |
| IAM role + instance profile | ECR pull, SSM params, S3 backups, CloudWatch logs, SSM agent |
| SSM Parameter Store (SecureString) | `SECRET_KEY`, `ANTHROPIC_API_KEY` |
| S3 bucket | Daily SQLite backups (30-day lifecycle) |
| CloudWatch log group | Container logs (`awslogs` driver) |
| CloudWatch alarms | Instance status-check + CPU > 80% |

Secrets are stored in SSM Parameter Store and injected into the container at
deploy time — they are **not** baked into the AMI, user-data, or the image.

## Usage

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # then edit (set app_secret_key)
terraform init
terraform plan
terraform apply
```

Outputs include `app_url`, `ecr_repository_url`, and `instance_id`.

The app image is built and pushed by CI (`.github/workflows/deploy.yml`), which
then runs `readmark-deploy.sh` on the instance via SSM. On first `apply` (before
any image exists) the container simply isn't running yet — the first CI deploy
starts it.

## Cost

~$0–10/month: t3.micro is free-tier eligible; ECR/S3/CloudWatch usage is minimal.
`terraform destroy` removes everything.

## Notes

- **State** is local for simplicity. For team use, add an S3 backend + DynamoDB
  lock in `versions.tf` and re-run `terraform init`.
- **Secrets** live in `terraform.tfvars` (gitignored) and SSM — never committed.
