# ADR 0001: EC2 + Docker over ECS/Fargate + RDS

- **Status:** Accepted
- **Date:** 2026-07

## Context

The AWS deployment of ReadMark needs to run one FastAPI container with a SQLite
database. Options considered:

1. **EC2 + Docker** — one instance running the container.
2. **ECS Fargate + RDS + ALB** — managed containers, managed Postgres, load balancer.
3. **App Runner + RDS** — fully managed containers; requires an external DB.

## Decision

Use **EC2 + Docker** with SQLite on the instance's EBS volume.

## Rationale

- **Simplicity.** The app is a single container with modest traffic. ECS/RDS/ALB
  add a VPC, subnets, task definitions, a managed DB, and a load balancer — more
  moving parts to operate for no current benefit.
- **Cost.** t3.micro is free-tier eligible; total ~$0–10/mo. Fargate + RDS + ALB
  is ~$40–70/mo minimum.
- **SQLite fit.** SQLite only needs a disk. App Runner/Fargate are ephemeral, so
  they would *force* a managed database purely for persistence.
- **Still demonstrates the platform.** IaC (Terraform), containers, IAM, SSM,
  ECR, CloudWatch, S3, and CI/CD are all exercised.

## Consequences

- **Single point of failure / no horizontal scaling** as-is. Acceptable at this
  scale; the mitigation is documented.
- **DB tied to one instance.** Mitigated by daily S3 backups + a restore runbook.
- **Clear upgrade path.** `DATABASE_URL` already abstracts the database, so
  moving to RDS Postgres and running behind an ALB across multiple instances (or
  ECS Fargate) is a config/infra change, not an app rewrite.

## Revisit when

Sustained traffic needs >1 instance, or an SLA requires multi-AZ redundancy.
