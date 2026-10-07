# Moving production to DigitalOcean

Written 2026-10-07. Production on AWS (`34.196.86.31`) is unreachable and the AWS
keys on the development Mac are invalid. This moves the site to one DigitalOcean
Droplet that runs the web app, the crawler and SQLite together, as on AWS.

Steps marked **(you)** need your DigitalOcean account. Everything else is in this
repo: `deploy/user-data.sh` provisions the server, `deploy/deploy.sh` ships code
and `deploy/backup/` takes daily backups.

## What to buy

| Item | Choice | Cost |
| --- | --- | --- |
| Droplet | Basic, Regular SSD, 2 GB / 1 vCPU / 50 GB, Ubuntu 24.04 LTS | $12/month |
| Backups | Spaces bucket, for daily off-server database copies | $5/month |
| DNS | Already on DigitalOcean (`emerssive.com`) | free |

Region: open DigitalOcean's speed-test pages for Frankfurt (FRA1) and Bangalore
(BLR1) from a connection in Pakistan and pick the faster one. Frankfurt is the
likely winner, because Pakistan's international routes mostly go west. Put the
Droplet and the Spaces bucket in the same region.

## 1. Create the Droplet (you)

1. Create → Droplets: Ubuntu 24.04, Basic 2 GB, your region, and your SSH key.
2. Under **Advanced options → Add initialization scripts**, paste the whole of
   `deploy/user-data.sh`. It installs Caddy, Python and SQLite, creates the
   `zrentals` user and the systemd services, enables a firewall for SSH, HTTP
   and HTTPS, and enables the daily backup timer.
3. Note the Droplet's IP address.

Check that provisioning finished:

```bash
ssh root@<droplet-ip> 'tail -3 /var/log/zameenrentals-bootstrap.log'
# expect: === Bootstrap complete, waiting for code deploy ===
```

## 2. Check that Zameen answers from the Droplet

Cloud IP ranges are sometimes blocked. Run one request before moving any data:

```bash
ssh root@<droplet-ip> 'curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0" \
  https://www.zameen.com/Rentals/Karachi_Clifton-5-1.html'
```

`200` means go ahead. A `403` or a timeout means the crawler can't run from this
IP; stop here and ask before going further.

## 3. Spaces and backup keys (you)

1. Create → Spaces Object Storage: a bucket named, say, `zameenrentals-backups`,
   in the same region as the Droplet.
2. Spaces Object Storage → Access Keys → create a key limited to that bucket.
3. Put the key on the Droplet:

```bash
ssh root@<droplet-ip> 'cat > /etc/zameenrentals/backup.env' <<'EOF'
ZR_BACKUP_ENDPOINT=https://fra1.digitaloceanspaces.com
ZR_BACKUP_BUCKET=zameenrentals-backups
AWS_DEFAULT_REGION=fra1
AWS_ACCESS_KEY_ID=<spaces key>
AWS_SECRET_ACCESS_KEY=<spaces secret>
EOF
```

Change `fra1` in both places if you chose another region.

## 4. Deploy the code

From the repo on your Mac:

```bash
ZR_DEPLOY_HOST=root@<droplet-ip> ZR_DEPLOY_KEY=~/.ssh/<your key> bash deploy/deploy.sh
```

This builds the frontend, copies the working tree (not git), installs Python
packages and restarts both services. It never copies `data/`.

If you have an `ANTHROPIC_API_KEY` for natural-language parsing, put it in
`/opt/zameenrentals/.env` (owned by `zrentals`, mode 600). Without it, the
regex parser runs.

## 5. Seed the database

Use the newest complete data you have, in this order of preference:

1. **An AWS snapshot**, if you get AWS access back. It also holds users' alerts,
   favorites and push subscriptions, which a crawl can't recreate. Download the
   newest `s3://zameenrentals/backups/zameenrentals-*.db.gz`, then `gunzip` it.
2. **The local rebuild** in `data/rebuild/`, once its re-crawl has finished. Take
   a consistent copy while the local crawler runs:

```bash
sqlite3 data/rebuild/zameenrentals.db ".backup /tmp/zameenrentals-seed.db"
```

Check the copy, then install it on the Droplet:

```bash
sqlite3 /tmp/zameenrentals-seed.db 'PRAGMA integrity_check; SELECT city, COUNT(*) FROM listings GROUP BY city;'
scp -i ~/.ssh/<your key> /tmp/zameenrentals-seed.db root@<droplet-ip>:/tmp/
ssh root@<droplet-ip> '
  systemctl stop zameenrentals-crawler zameenrentals-web
  install -o zrentals -g zrentals -m 640 /tmp/zameenrentals-seed.db /opt/zameenrentals/data/zameenrentals.db
  systemctl start zameenrentals-web zameenrentals-crawler'
```

Push notification keys (`data/vapid_*`) are generated on first start. Browsers
subscribed under the old AWS keys need to subscribe again, unless you restore
the old key pair from the AWS server.

## 6. Point the domain at the Droplet (you)

In DigitalOcean → Networking → Domains → `emerssive.com`, change the A record for
`zameenrentals` from `34.196.86.31` to the Droplet IP. Caddy requests the HTTPS
certificate itself once DNS resolves to the Droplet.

## 7. Check it works

```bash
curl -s https://zameenrentals.emerssive.com/api/health
curl -s 'https://zameenrentals.emerssive.com/api/search?city=karachi&area=DHA+Phase+6' | head -c 300
ssh root@<droplet-ip> 'journalctl -u zameenrentals-crawler -n 20 --no-pager'
ssh root@<droplet-ip> 'systemctl start zameenrentals-backup.service; journalctl -u zameenrentals-backup -n 5 --no-pager'
```

The last command runs one backup now; expect `OK: uploaded s3://zameenrentals-backups/...`.

## 8. Shut down AWS (you)

After the new site has run cleanly for a few days, stop the old EC2 instance
(`i-0a3e39132e2a9c3ef`) and release Elastic IP `34.196.86.31`, or AWS keeps
billing for both. Download any S3 backups you want to keep first.
