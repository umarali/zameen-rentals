# ZameenRentals DB backups

Daily off-site backup of the production SQLite DB to S3 or any S3-compatible
store, such as DigitalOcean Spaces.

## What runs
- **`zameenrentals-backup.py`** — installed at `/usr/local/bin/` on the instance.
  Takes a WAL-safe snapshot via the sqlite3 online-backup API (safe while the
  crawler writes), gzips it, and uploads to
  `s3://zameenrentals/backups/zameenrentals-YYYY-MM-DD.db.gz`.
- **`zameenrentals-backup.timer` / `.service`** — installed in
  `/etc/systemd/system/`. The timer fires daily at ~03:00 UTC
  (`Persistent=true`, so a run missed while the box was off catches up on boot).

## Auth on DigitalOcean (Spaces)
Droplets have no instance role, so the job reads a Spaces access key from
`/etc/zameenrentals/backup.env` (root-owned, mode 600; systemd loads it before
dropping to `zrentals`):

```
ZR_BACKUP_ENDPOINT=https://fra1.digitaloceanspaces.com
ZR_BACKUP_BUCKET=zameenrentals-backups
AWS_DEFAULT_REGION=fra1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Limit the key to the backup bucket. Set retention with a lifecycle rule on the
bucket; `s3-lifecycle.json` works with Spaces too. Full setup:
[`docs/digitalocean-deployment.md`](../../docs/digitalocean-deployment.md).

## Auth on AWS (no static keys)
The instance has IAM role **`zameenrentals-backup-role`** (instance profile
`zameenrentals-backup-profile`) with an inline policy scoped to `s3:PutObject` +
`s3:ListBucket` on `s3://zameenrentals/backups/*` only — **no `DeleteObject`**,
so the job can never remove existing backups. boto3 reads these credentials from
IMDS automatically; nothing is stored on disk.

## Retention
S3 lifecycle rule `expire-zameenrentals-backups-180d` expires objects under
`backups/` after 180 days. Policy doc: [`s3-lifecycle.json`](s3-lifecycle.json).

## Restore
```bash
aws s3 cp s3://zameenrentals/backups/zameenrentals-YYYY-MM-DD.db.gz /tmp/
gunzip /tmp/zameenrentals-YYYY-MM-DD.db.gz
# verify before swapping in:
sqlite3 /tmp/zameenrentals-YYYY-MM-DD.db 'PRAGMA integrity_check; SELECT COUNT(*) FROM listings;'
# on the box (as zrentals), pause the writer, swap, resume:
sudo systemctl stop zameenrentals-crawler
sudo -u zrentals cp /tmp/zameenrentals-YYYY-MM-DD.db /opt/zameenrentals/data/zameenrentals.db
sudo systemctl start zameenrentals-crawler
```

## Reprovision (fresh instance)
`deploy/user-data.sh` recreates the script + units and enables the timer at
boot; `boto3` is installed into the venv from `requirements.txt` on the first
code deploy. The IAM role / instance profile and the S3 lifecycle rule are
account-level and persist independently of the instance. To recreate them from
scratch:

```bash
aws iam create-role --role-name zameenrentals-backup-role \
  --assume-role-policy-document file://deploy/backup/iam-trust-policy.json
aws iam put-role-policy --role-name zameenrentals-backup-role \
  --policy-name zameenrentals-s3-backup-write \
  --policy-document file://deploy/backup/iam-s3-backup-policy.json
aws iam create-instance-profile --instance-profile-name zameenrentals-backup-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name zameenrentals-backup-profile \
  --role-name zameenrentals-backup-role
aws ec2 associate-iam-instance-profile --instance-id <id> \
  --iam-instance-profile Name=zameenrentals-backup-profile --region us-east-1
aws s3api put-bucket-lifecycle-configuration --bucket zameenrentals \
  --lifecycle-configuration file://deploy/backup/s3-lifecycle.json
```

## Files
| File | Purpose |
| --- | --- |
| `zameenrentals-backup.py` | the backup script (also embedded in `user-data.sh`; `tests/test_deploy_files.py` checks they match) |
| `zameenrentals-backup.service` / `.timer` | systemd units |
| `iam-trust-policy.json` | EC2 assume-role trust |
| `iam-s3-backup-policy.json` | scoped S3 write policy (no delete) |
| `s3-lifecycle.json` | 180-day retention rule |
