# Runbook: Backup & Restore

The database is SQLite. Backups are consistent hot snapshots (SQLite online
backup API) taken daily and uploaded to S3.

## Backups

- **What:** `/data/readmark.db` inside the container.
- **How:** `/usr/local/bin/readmark-backup.sh` (installed by user-data).
- **When:** daily 03:15 via `/etc/cron.d/readmark-backup`.
- **Where:** `s3://readmark-backups-<account-id>/readmark-<timestamp>.db.gz`
- **Retention:** 30 days (S3 lifecycle rule).

Run one on demand:

```bash
aws ssm start-session --target <INSTANCE_ID>
sudo /usr/local/bin/readmark-backup.sh
```

List backups:

```bash
aws s3 ls s3://readmark-backups-<account-id>/ --recursive | sort | tail
```

## Verify a backup

```bash
aws s3 cp s3://readmark-backups-<account-id>/readmark-<ts>.db.gz /tmp/
gunzip -f /tmp/readmark-<ts>.db.gz
python3 -c "import sqlite3;c=sqlite3.connect('/tmp/readmark-<ts>.db');\
print('users:', c.execute('select count(*) from users').fetchone()[0]);\
print('items:', c.execute('select count(*) from reading_items').fetchone()[0])"
```

## Restore

```bash
aws ssm start-session --target <INSTANCE_ID>

# 1. Fetch the chosen backup onto the box
aws s3 cp s3://readmark-backups-<account-id>/readmark-<ts>.db.gz /tmp/
gunzip -f /tmp/readmark-<ts>.db.gz

# 2. Stop the app so the DB file isn't in use
sudo docker stop readmark

# 3. Replace the live DB (keep the current one aside first)
sudo cp /opt/readmark/data/readmark.db /opt/readmark/data/readmark.db.bak
sudo cp /tmp/readmark-<ts>.db /opt/readmark/data/readmark.db

# 4. Start again and verify
sudo docker start readmark
curl -fsS http://localhost:8000/api/ready
```

## Notes

- Test restores periodically — an unverified backup is not a backup.
- For point-in-time needs, increase backup frequency (cron) or move to RDS with
  automated snapshots + PITR.
