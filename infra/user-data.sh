#!/usr/bin/env bash
# ReadMark EC2 bootstrap. Rendered by Terraform templatefile(): a bare
# dollar-brace is substituted by Terraform now; a doubled dollar-brace
# survives as a literal for bash to evaluate at runtime.
set -euxo pipefail

# ── Base packages ─────────────────────────────────────────────────────────
dnf update -y
dnf install -y docker cronie unzip
systemctl enable --now docker
systemctl enable --now crond

if ! command -v aws >/dev/null 2>&1; then
  curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install
fi

# ── Config for the helper scripts (Terraform values, substituted now) ─────
cat > /etc/readmark.env <<EOF
PROJECT=${project}
REGION=${region}
ECR_REPO=${ecr_repo_url}
LOG_GROUP=${log_group}
BACKUPS_BUCKET=${backups_bucket}
ALLOWED_ORIGINS=${allowed_origins}
AI_MODEL=${ai_model}
EOF

# The container runs as non-root uid 10001 (see backend/Dockerfile); the mounted
# data dir must be writable by that uid or SQLite can't open its file.
mkdir -p /opt/${project}/data
chown -R 10001:10001 /opt/${project}/data

# ── Deploy script (quoted heredoc: written verbatim, runs at deploy time) ──
cat > /usr/local/bin/readmark-deploy.sh <<'DEPLOY'
#!/usr/bin/env bash
set -euo pipefail
source /etc/readmark.env
REGISTRY="$${ECR_REPO%%/*}"

aws ecr get-login-password --region "$${REGION}" | docker login --username AWS --password-stdin "$${REGISTRY}"
docker pull "$${ECR_REPO}:latest"

SECRET_KEY="$(aws ssm get-parameter --region "$${REGION}" --name "/$${PROJECT}/SECRET_KEY" --with-decryption --query Parameter.Value --output text)"
ANTHROPIC_API_KEY="$(aws ssm get-parameter --region "$${REGION}" --name "/$${PROJECT}/ANTHROPIC_API_KEY" --with-decryption --query Parameter.Value --output text)"
[ "$${ANTHROPIC_API_KEY}" = "unset" ] && ANTHROPIC_API_KEY=""

docker rm -f readmark 2>/dev/null || true
docker run -d --name readmark --restart unless-stopped \
  -p 8000:8000 \
  -v "/opt/$${PROJECT}/data:/data" \
  -e DATABASE_URL="sqlite+aiosqlite:////data/readmark.db" \
  -e SECRET_KEY="$${SECRET_KEY}" \
  -e ALLOWED_ORIGINS="$${ALLOWED_ORIGINS}" \
  -e ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY}" \
  -e AI_MODEL="$${AI_MODEL}" \
  --log-driver=awslogs \
  --log-opt awslogs-region="$${REGION}" \
  --log-opt awslogs-group="$${LOG_GROUP}" \
  --log-opt awslogs-create-group=true \
  "$${ECR_REPO}:latest"
echo "deployed $${ECR_REPO}:latest"
DEPLOY
chmod +x /usr/local/bin/readmark-deploy.sh

# ── Backup script (SQLite snapshot -> S3) ─────────────────────────────────
cat > /usr/local/bin/readmark-backup.sh <<'BACKUP'
#!/usr/bin/env bash
set -euo pipefail
source /etc/readmark.env
STAMP="$(date +%Y%m%d-%H%M%S)"
docker exec readmark python -c "import sqlite3;s=sqlite3.connect('/data/readmark.db');d=sqlite3.connect('/data/_backup.db');s.backup(d);d.close();s.close()"
docker cp readmark:/data/_backup.db "/tmp/readmark-$${STAMP}.db"
docker exec readmark rm -f /data/_backup.db
gzip -f "/tmp/readmark-$${STAMP}.db"
aws s3 cp "/tmp/readmark-$${STAMP}.db.gz" "s3://$${BACKUPS_BUCKET}/readmark-$${STAMP}.db.gz" --region "$${REGION}"
rm -f "/tmp/readmark-$${STAMP}.db.gz"
echo "backup uploaded"
BACKUP
chmod +x /usr/local/bin/readmark-backup.sh

echo "15 3 * * * root /usr/local/bin/readmark-backup.sh >> /var/log/readmark-backup.log 2>&1" > /etc/cron.d/readmark-backup

# ── Optional HTTPS via Caddy (auto Let's Encrypt) ─────────────────────────
DOMAIN="${domain}"
if [ -n "$${DOMAIN}" ]; then
  curl -sfL -o /usr/bin/caddy "https://caddyserver.com/api/download?os=linux&arch=amd64"
  chmod +x /usr/bin/caddy
  mkdir -p /etc/caddy /var/lib/caddy
  cat > /etc/caddy/Caddyfile <<'CADDY'
${domain} {
    reverse_proxy localhost:8000
}
CADDY
  cat > /etc/systemd/system/caddy.service <<'UNIT'
[Unit]
Description=Caddy
After=network.target
[Service]
Environment=XDG_DATA_HOME=/var/lib/caddy
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now caddy
fi

# ── First deploy (no-op if no image pushed yet) ───────────────────────────
/usr/local/bin/readmark-deploy.sh || echo "no image yet — CI/CD will deploy"
