#!/bin/bash
# Wazi — VPS Security Hardening
# Run AFTER vps_setup.sh, as root, on the Ubuntu 24.04 VPS:
#   chmod +x scripts/harden_vps.sh && ./scripts/harden_vps.sh
#
# Idempotent — safe to re-run. Covers the automatable half of the Day 10-12
# security checklist. The two items that can lock you out or need a domain
# (SSH key-only auth, HTTPS) are LEFT MANUAL on purpose — see
# docs/security-hardening.md.
set -euo pipefail

echo "=== Wazi VPS Hardening ==="

# 1. Lock down .env — it holds the DB password, DeepSeek key, and ID_SALT.
if [ -f /opt/wazi/.env ]; then
    chmod 600 /opt/wazi/.env
    chown root:root /opt/wazi/.env
    echo "[ok] /opt/wazi/.env -> 600 root:root (secrets not world-readable)"
else
    echo "[warn] /opt/wazi/.env not found — run vps_setup.sh first"
fi

# 2. PostgreSQL: assert localhost-only binding (defence in depth).
PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
if [ -n "${PG_CONF}" ]; then
    if grep -qE "^\s*listen_addresses\s*=\s*'localhost'" "${PG_CONF}"; then
        echo "[skip] PostgreSQL already bound to localhost"
    else
        sed -i "s/^#*\s*listen_addresses.*/listen_addresses = 'localhost'/" "${PG_CONF}"
        systemctl restart postgresql
        echo "[ok] PostgreSQL bound to localhost only"
    fi
fi

# 3. fail2ban — bans IPs after repeated failed SSH logins.
apt install -y -qq fail2ban
systemctl enable --now fail2ban
echo "[ok] fail2ban active (SSH brute-force protection)"

# 4. Unattended security upgrades — patches land without manual apt.
apt install -y -qq unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
echo "[ok] automatic security updates enabled"

# 5. Firewall — assert only 22/80/443 are open. FastAPI (8000) and
#    PostgreSQL (5432) stay internal, reachable only via Nginx / localhost.
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "[ok] firewall: 22/80/443 exposed; 8000 + 5432 internal-only"

# 6. Nginx rate-limit zone for the webhook. Declared here; applied to the
#    /whatsapp/incoming location by a one-liner in docs (kept manual so this
#    script never rewrites the server block vps_setup.sh owns).
RL_CONF=/etc/nginx/conf.d/wazi_ratelimit.conf
if [ ! -f "${RL_CONF}" ]; then
    cat > "${RL_CONF}" << 'EOF'
# 10 req/s per IP, burst 20. Africa's Talking delivers from a small IP set,
# so this caps floods without dropping legitimate webhook traffic. Pair with
# the app-level anti-bot guards in src/api/middleware/anti_bot.py.
limit_req_zone $binary_remote_addr zone=wazi_webhook:10m rate=10r/s;
EOF
    nginx -t && systemctl reload nginx
    echo "[ok] nginx rate-limit zone added (apply to location — see docs)"
else
    echo "[skip] nginx rate-limit zone already present"
fi

echo ""
echo "=== Automated hardening complete ==="
echo ""
echo "MANUAL steps remaining (need human judgement — docs/security-hardening.md):"
echo "  1. SSH key-only auth — TEST the key in a SECOND terminal BEFORE"
echo "     disabling password auth, or you can lock yourself out."
echo "  2. HTTPS — needs a domain name; Let's Encrypt will not issue a"
echo "     certificate for a bare IP (157.230.232.223)."
