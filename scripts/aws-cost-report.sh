#!/usr/bin/env bash
# FinOps: month-to-date AWS spend by service, plus the app's AI spend.
# Usage: scripts/aws-cost-report.sh [region]
set -euo pipefail

REGION="${1:-us-east-1}"
START="$(date -u +%Y-%m-01)"
END="$(date -u +%Y-%m-%d)"
[ "$START" = "$END" ] && END="$(date -u -d "$START +1 day" +%Y-%m-%d 2>/dev/null || echo "$START")"

echo "AWS cost by service — $START to $END"
echo "----------------------------------------"
aws ce get-cost-and-usage \
  --time-period "Start=$START,End=$END" \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[0].Groups[?Metrics.UnblendedCost.Amount!=`0`].[Keys[0],Metrics.UnblendedCost.Amount]' \
  --output table 2>/dev/null || echo "(Cost Explorer not enabled or no permission)"

echo
echo "ReadMark AI spend (from the app's own metrics):"
APP_URL="${APP_URL:-http://localhost:8000}"
if curl -fsS "$APP_URL/metrics" >/tmp/m 2>/dev/null; then
  grep '^readmark_ai_cost_usd_total' /tmp/m || echo "  (no AI spend recorded yet)"
  rm -f /tmp/m
else
  echo "  (set APP_URL to the running app to read live AI cost metrics)"
fi

echo
echo "Tip: EC2 t3.micro is free-tier eligible; keep ECR images pruned (lifecycle"
echo "policy keeps last 10) and S3 backups on the 30-day lifecycle to control cost."
