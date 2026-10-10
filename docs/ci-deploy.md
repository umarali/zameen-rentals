# Deploy on merge (GitHub Actions)

`.github/workflows/deploy.yml` deploys production every time `main` changes.
It does what a manual deploy does, from a clean checkout of the merged commit:

1. **Resolve**: pick the commit (the pushed `main` head, or the `ref` input on
   a manual run) and refuse anything that is not on `main`'s history.
2. **Tests**: pytest (all of `tests/` except `test_claude_integration.py`,
   including the real Whisper model tests) and the headless Playwright suite.
3. **Deploy**: in the `production` environment, run `deploy/deploy.sh`
   unchanged, then the smoke check: `/api/health` must return 200 and the
   live `/` must reference the `index-*.js` bundle this run built.

Only one deploy runs at a time and a running deploy is never cancelled. If a
newer commit lands on `main` while an older run is still testing, the older run
skips its deploy, so it can't overwrite the newer code.

## One-time setup

Do these **before merging the PR that adds the workflow**. That merge is a push
to `main` and starts the first deploy. Without the secrets, it fails at
"Install SSH key" and nothing is deployed.

### 1. Authorize the deploy key on the Droplet

The deploy key is a separate ed25519 key used only by GitHub Actions. Its
private half is `~/.ssh/zameenrentals_gha_deploy` on the development Mac
(public fingerprint `SHA256:zPqPjJU2JhuTshEJJx1Fij12JpnTDxDub/4lt/zCjiM`).
Append the public key to root's `authorized_keys`, prefixed with `restrict`.
That turns off port, agent and X11 forwarding and PTY allocation. `deploy.sh`
needs only plain commands and rsync.

```bash
{ printf 'restrict '; cat ~/.ssh/zameenrentals_gha_deploy.pub; } \
  | ssh -i ~/.ssh/id_ed25519 root@165.22.91.77 'cat >> /root/.ssh/authorized_keys'

# Check it: expect "ok"
ssh -i ~/.ssh/zameenrentals_gha_deploy -o IdentitiesOnly=yes root@165.22.91.77 'echo ok'
```

A `from="..."` source restriction isn't practical, because GitHub-hosted
runners use large, changing IP ranges. A forced `command=` would break
`deploy.sh`, which runs rsync and a shell script.

### 2. Add the repository secrets

```bash
# Private deploy key. gh reads it from the file; it is never printed.
gh secret set DEPLOY_SSH_KEY -R umarali/zameen-rentals < ~/.ssh/zameenrentals_gha_deploy

# The Droplet's host keys, from the known_hosts entry this Mac already trusts.
ssh-keygen -F 165.22.91.77 | grep -v '^#' \
  | gh secret set DEPLOY_KNOWN_HOSTS -R umarali/zameen-rentals
```

The ed25519 host key's fingerprint is
`SHA256:o3MJBKS0w1ACwGNVRYZfH+LunDSddqM3tPc84o84OJQ`; check it with
`ssh-keygen -F 165.22.91.77 | grep ed25519 | ssh-keygen -lf -`. If the Droplet
is ever rebuilt, its host key changes. Update this secret, otherwise deploys
stop with `Host key verification failed`.

Optional: to scope the secrets to deploys only, add `--env production` to both
commands after step 3, which makes them environment secrets.

Once the deploy key works from Actions, the personal key no longer needs to be
used for deploys.

### 3. Create the `production` environment

GitHub → Settings → Environments → **New environment** → `production`:

- **Required reviewers**: add yourself, if each deploy should wait for a click.
  Leave "Prevent self-review" off, since you are the only reviewer.
- **Deployment branches and tags**: Selected branches → `main`. This stops a
  run started from any other branch from reaching production.

If the environment doesn't exist, the first run creates it with no protection.

### 4. Analytics (optional)

The live site is built without PostHog today. To turn analytics on, add
repository **variables** (not secrets; the key is public in the bundle)
`VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST`. The next deploy builds them in.

## Roll back

Redeploy an earlier `main` commit:

```bash
gh workflow run deploy.yml -R umarali/zameen-rentals --ref main -f ref=<commit-sha>
```

Or: Actions → Deploy → Run workflow → "Use workflow from: main" → enter the
SHA. Find it with `git log --first-parent origin/main`. The run tests that
commit, deploys it and smoke-checks it. The next merge to `main` deploys the
new head again, so revert the bad change on `main` as well.

A rollback ships code only. `data/` (the SQLite database) is never touched, so a
schema change made by the newer code stays in place.

## Manual deploys still work

`deploy/deploy.sh` is unchanged. From a clean `main` checkout:

```bash
ZR_DEPLOY_HOST=root@165.22.91.77 ZR_DEPLOY_KEY=~/.ssh/id_ed25519 bash deploy/deploy.sh
```

A manual deploy can overlap a CI deploy. Check the Actions tab first.
