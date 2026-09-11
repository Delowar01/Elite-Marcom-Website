# Deploying Elite One Desk to a Hostinger VPS

Ubuntu 22.04 or 24.04, Node.js LTS, PostgreSQL, nginx, Let's Encrypt, and either
systemd or PM2.

Everything below assumes this layout, which is what the shipped configuration
files expect:

```
/var/www/elite-one-desk/
├── app/          the repository — replaced on every release
└── uploads/      the media library — NEVER inside app/
/var/backups/elite-one-desk/
```

**The uploads directory sits outside `app/` on purpose.** A release replaces the
application directory; anything inside it goes with the old release. An uploaded
photograph exists nowhere else.

---

## 1. Prepare the server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git nginx postgresql postgresql-contrib ufw

# Node.js 22 LTS
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node -v

# Firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

Create the account the application runs as. It owns nothing it does not need:

```bash
sudo adduser --system --group --home /var/www/elite-one-desk eliteonedesk
sudo mkdir -p /var/www/elite-one-desk/{app,uploads} /var/log/elite-one-desk
sudo chown -R eliteonedesk:eliteonedesk /var/www/elite-one-desk /var/log/elite-one-desk
```

## 2. PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE elite_one_desk LOGIN PASSWORD 'put-a-long-random-password-here';
CREATE DATABASE elite_one_desk OWNER elite_one_desk;
SQL
```

The database listens on localhost only by default. Leave it that way — nothing
outside this machine needs to reach it.

## 3. First release

```bash
sudo -u eliteonedesk -H bash
cd /var/www/elite-one-desk
git clone https://github.com/<owner>/<repo>.git app
cd app/elite-one-desk        # this project lives in a subdirectory of the repo

npm ci --omit=dev --ignore-scripts
npm rebuild sharp            # --ignore-scripts skips its platform binary
```

> If you prefer the application at `/var/www/elite-one-desk/app` directly, clone
> elsewhere and symlink or copy this subdirectory there. The shipped nginx and
> systemd files assume `app/` is the Next.js project root.

### Environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

| Variable | |
|---|---|
| `DATABASE_URL` | `postgres://elite_one_desk:…@127.0.0.1:5432/elite_one_desk` |
| `NEXT_PUBLIC_SITE_URL` | `https://eliteonedesk.com` — no trailing slash |
| `AUTH_SECRET` | `openssl rand -base64 48` |
| `UPLOAD_DIR` | `/var/www/elite-one-desk/uploads` |
| `SEED_OWNER_EMAIL` / `SEED_OWNER_PASSWORD` / `SEED_OWNER_NAME` | The first owner account |

`.env` is git-ignored and must stay that way. The owner seed values are only read
when no user exists at all; clear them once the account is created.

### Build, migrate, seed

```bash
npm run build
npm run db:migrate
npm run db:seed

# `output: standalone` does not copy these; without them there are no
# stylesheets and no fonts.
cp -r .next/static .next/standalone/.next/static
cp -r public       .next/standalone/public
```

Check it before putting nginx in front of it:

```bash
PORT=3000 node .next/standalone/server.js &
curl -I http://127.0.0.1:3000/
kill %1
```

## 4. Process manager

Pick **one**.

### systemd (recommended)

```bash
exit   # back to your sudo user
sudo cp /var/www/elite-one-desk/app/deploy/elite-one-desk.service /etc/systemd/system/
sudo nano /etc/systemd/system/elite-one-desk.service   # check WorkingDirectory
sudo systemctl daemon-reload
sudo systemctl enable --now elite-one-desk
sudo systemctl status elite-one-desk
sudo journalctl -u elite-one-desk -f
```

### PM2

```bash
sudo npm install -g pm2
sudo -u eliteonedesk -H pm2 start /var/www/elite-one-desk/app/deploy/ecosystem.config.js
sudo -u eliteonedesk -H pm2 save
sudo pm2 startup systemd -u eliteonedesk --hp /var/www/elite-one-desk
```

## 5. nginx

```bash
sudo cp /var/www/elite-one-desk/app/deploy/nginx.conf /etc/nginx/sites-available/elite-one-desk
sudo nano /etc/nginx/sites-available/elite-one-desk     # set server_name and paths
sudo ln -s /etc/nginx/sites-available/elite-one-desk /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

The configuration serves `/media/`, `/_next/static/`, `/fonts/` and `/brand/`
straight off disk and proxies everything else. It deliberately does **not** add a
`Content-Security-Policy` header: the application sets its own with a per-request
nonce, and an nginx header would override it with something weaker.

## 6. HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d eliteonedesk.com -d www.eliteonedesk.com
sudo systemctl status certbot.timer     # renewal is automatic
```

## 7. File permissions

```bash
sudo chown -R eliteonedesk:eliteonedesk /var/www/elite-one-desk
sudo chmod 750 /var/www/elite-one-desk/uploads
sudo chmod 600 /var/www/elite-one-desk/app/.env

# nginx reads the upload directory directly, so it needs to traverse the path.
sudo usermod -aG eliteonedesk www-data
sudo systemctl restart nginx
```

## 8. Backups

```bash
sudo mkdir -p /var/backups/elite-one-desk
sudo install -m 0755 /var/www/elite-one-desk/app/deploy/backup.sh /usr/local/bin/elite-one-desk-backup
sudo crontab -e
```

```cron
15 2 * * *  /usr/local/bin/elite-one-desk-backup >> /var/log/elite-one-desk/backup.log 2>&1
```

The script dumps PostgreSQL, archives the uploads, verifies the dump is readable
and prunes anything older than 30 days.

**Copy the results off the machine.** A backup that lives on the server it is
protecting is not a backup. Hostinger's snapshots plus an `rclone`/`rsync` job to
object storage covers both failure modes.

Restoring:

```bash
gunzip -c /var/backups/elite-one-desk/db-YYYYMMDD-HHMMSS.sql.gz \
  | psql "postgres://elite_one_desk:…@127.0.0.1:5432/elite_one_desk"
tar -xzf /var/backups/elite-one-desk/uploads-YYYYMMDD-HHMMSS.tar.gz -C /var/www/elite-one-desk/
```

## 9. Updating

```bash
sudo -u eliteonedesk -H bash
cd /var/www/elite-one-desk/app
./deploy/deploy.sh
```

It fetches, installs, builds, migrates, re-runs the seed (which adds anything new
and overwrites nothing), copies the static assets next to the standalone server,
restarts, and checks the site answers before exiting.

Order matters: **build first, migrate second, restart last.** A failed build
leaves the running site untouched.

## 10. After the first deployment

1. Sign in at `https://eliteonedesk.com/admin` with the owner account.
2. **Change the owner password** and clear `SEED_OWNER_*` from `.env`.
3. **Site settings → Contact** — address, phone, email, hours, map. Every field
   left empty renders as nothing; nothing is invented to fill a gap.
4. **Site settings → WhatsApp** — the number, then switch it on. The floating
   button and every WhatsApp link stay hidden until both are set.
5. **Site settings → Social links** — https addresses only.
6. **Site settings → Disclaimers** — read them with your legal adviser. They are
   what keep the site from reading as an official government channel.
7. **Pages → Privacy, Terms, Disclaimer** — the shipped text is a starting draft.
8. **Analytics** — add the GA4 or Tag Manager id if you have one. Nothing loads
   until you do, so this is also the decision about whether to load anything.
9. **Media library** — replace the generated artwork with photography when you
   have it. Nothing in code refers to those files by name.
10. **Users & roles** — create accounts for the team. Give the smallest role that
    does the job; it can always be raised.

## Troubleshooting

**502 from nginx** — the app is not running. `sudo journalctl -u elite-one-desk -n 50`.

**Images 404** — the `alias` in nginx must match `UPLOAD_DIR` exactly, trailing
slash included. Confirm `www-data` can traverse the path.

**Styles missing after a release** — `.next/static` and `public` were not copied
next to the standalone server. `deploy/deploy.sh` does this; if you built by
hand, do it by hand.

**`AUTH_SECRET must be at least 32 characters`** — it is unset or too short.
`openssl rand -base64 48`. Changing it signs everyone out, which is harmless.

**Migrations fail** — check `DATABASE_URL` and that the role owns the database.
`npm run db:migrate` is safe to re-run; it applies only what is pending.

**An editor cannot see a screen** — that is the permission model working. Users &
roles → the permission matrix.
