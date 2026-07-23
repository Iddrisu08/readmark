# Runbook: Incident Response

For the AWS deployment. Goal: restore service quickly, then find root cause.

## 0. Triage (first 2 minutes)

```bash
# Is the app up?
curl -fsS http://<APP_IP>:8000/api/health   # liveness
curl -fsS http://<APP_IP>:8000/api/ready     # readiness (DB reachable)
```

- **health fails** → the container/instance is down → go to §1.
- **ready fails but health ok** → DB problem → go to §2.
- **both ok but users report errors** → check logs (§3) and metrics (§4).

## 1. App/container down

```bash
# Connect (Session Manager — no SSH needed)
aws ssm start-session --target <INSTANCE_ID>

sudo docker ps -a                       # is the container running / crashed?
sudo docker logs --tail 100 readmark    # why did it exit?
sudo systemctl status docker            # is Docker itself up?

# Restart the app
sudo /usr/local/bin/readmark-deploy.sh
```

If the instance itself is unhealthy, check the CloudWatch alarm
`readmark-status-check-failed` and reboot from the EC2 console.

## 2. Database not ready

```bash
sudo docker exec readmark ls -la /data/readmark.db   # exists? size?
df -h                                                # disk full?
```

- Disk full → clear old files / grow the EBS volume.
- DB corrupt/missing → restore from backup (see `backup-restore.md`).

## 3. Reading logs

```bash
# On the box:
sudo docker logs --tail 200 -f readmark
# Or in CloudWatch Logs: log group /readmark/app  (structured JSON)
```

Logs are JSON — filter by field, e.g. errors:
`aws logs tail /readmark/app --filter-pattern '{ $.level = "ERROR" }' --follow`

## 4. Metrics

`http://<APP_IP>:8000/metrics` (Prometheus). Watch:
- `http_requests_total{status="5xx"}` — error rate.
- `readmark_ai_requests_total{status="error"}` — AI/provider failures.
- `readmark_ai_cost_usd_total` — unexpected spend spikes.

## 5. AI provider issues

If summarization errors spike: the app degrades gracefully (summaries fail with
502, the rest of the app is unaffected). Check the Anthropic status page and the
`ANTHROPIC_API_KEY` SSM parameter. Disable the feature by clearing the key and
redeploying if needed.

## 6. After recovery

- Note timeline, impact, root cause.
- File a follow-up to prevent recurrence.
- If secrets were exposed, rotate them in SSM and redeploy.
