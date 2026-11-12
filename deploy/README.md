# Deploying license_server.py

This is the **central control plane** for Vilona AI. It runs on a fixed host,
exposes `/license/*` + `/relay/*`, and is what the TGCloud bot drives.

## One-time setup on this host

```bash
# 1. Generate production secrets (do NOT commit)
cat >> .env.local <<EOF
vilona_LICENSE_ADMIN_TOKEN=$(openssl rand -hex 24)
vilona_RELAY_BOT_TOKEN=$(openssl rand -hex 24)
vilona_LICENSE_DB=/home/openclaw/projects/vilona-ai/data/licenses.db
vilona_LICENSE_PORT=8301
EOF
chmod 600 .env.local

# 2. Install systemd unit
sudo cp deploy/vilona-license-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vilona-license-relay

# 3. Route public traffic (1ai-cf-router)
sudo cp deploy/nginx-app_vilona-relay.conf /home/openclaw/.cloudflare-router/nginx/sites/app_vilona-relay.conf
sudo tee -a /home/openclaw/.cloudflare-router/nginx/sites-active.conf \
  <<< "include /home/openclaw/.cloudflare-router/nginx/sites/app_vilona-relay.conf;"

# 4. Add DNS hostname in the cloudflared tunnel config (see /etc/cloudflared/config.yml)
#    - hostname: vilona-relay.aitradepulse.com
#      service: http://localhost:6969

# 5. Reload
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl restart cloudflared
```

Then verify:

```bash
curl https://vilona-relay.aitradepulse.com/healthz
```

Should return `{"ok": true, "count": N}`.

## Rotating tokens

Edit `.env.local`, `sudo systemctl restart vilona-license-relay`.

## Rollback

```bash
sudo systemctl stop vilona-license-relay
sudo rm /home/openclaw/.cloudflare-router/nginx/sites/app_vilona-relay.conf
sudo systemctl reload nginx
```
