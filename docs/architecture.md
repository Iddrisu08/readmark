# ReadMark — Architecture

ReadMark is a read-it-later service: a browser extension + web app backed by a
FastAPI service with an optional Claude-powered summarization feature.

## Components

| Component | Tech | Notes |
|---|---|---|
| Extension | JS, Chrome MV3 | Saves pages, tracks reading progress |
| Web app / dashboard | Static HTML/JS (served by backend at `/`) | Full client + PWA |
| API | FastAPI (Python), async SQLAlchemy | Auth (JWT), items, AI |
| Database | SQLite (async) | One file; backed up to S3/local |
| AI | Anthropic Claude (`ai.py`) | Article summarization + cost tracking |
| Observability | JSON logs + Prometheus `/metrics` | HTTP + AI usage/cost metrics |

## Request flow

```
Browser extension ─┐
Web dashboard ─────┼─► ALB/Caddy (HTTPS) ─► FastAPI :8000 ─► SQLite
                   │                          │
                   │                          └─► Claude API (summaries)
                   └─ Authorization: Bearer <JWT>
```

## Deployments

There are two independent deployments of the same codebase:

### 1. DigitalOcean droplet (original / live)
- Docker Compose + Caddy (auto HTTPS) at `https://getreadmark.com`.
- SQLite on the host; daily backups on-box.
- Documented in the root `README` and `deploy` history.

### 2. AWS (this repo's `infra/` — IaC-managed)
```
GitHub ─push─► Actions
  ├─ CI: ruff + pytest
  ├─ Deploy: build image ─► ECR ─► SSM run-command ─► EC2
  └─ Terraform: fmt/validate/plan

AWS (us-east-1, default VPC):
  EC2 t3.micro (Docker) ── SQLite on EBS
    ├─ pulls image from ECR
    ├─ secrets from SSM Parameter Store (SecureString)
    ├─ container logs ─► CloudWatch Logs
    └─ daily SQLite snapshot ─► S3 (30-day lifecycle)
  CloudWatch alarms: status-check, CPU>80%
```

- Provisioned entirely by Terraform (`infra/`).
- Deploys via GitHub Actions → ECR → SSM (no SSH in the deploy path).
- Secrets never touch git, the AMI, or the image — they live in SSM and are
  injected at container start.

## Key design choices

- **EC2 + Docker over ECS/RDS** — deliberately simple and low-cost for a
  single-instance app; SQLite needs only a disk. See `docs/adr/0001-*`.
- **SSM over SSH for deploys** — no inbound SSH or key distribution required.
- **SQLite over a managed DB** — zero operational overhead at this scale;
  `DATABASE_URL` allows moving to Postgres later with no code change.

## Scaling / evolution path

If load grows: move `DATABASE_URL` to RDS Postgres, run the container behind an
ALB across ≥2 instances (or ECS Fargate), and add an ElastiCache/session layer.
None of this requires application code changes.
