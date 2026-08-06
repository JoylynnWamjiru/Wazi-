#!/bin/bash
# Wazi — VPS Setup Script
# Run on Ubuntu 24.04 as root:
#   chmod +x scripts/vps_setup.sh
#   ./scripts/vps_setup.sh
#
# This script installs PostgreSQL 16 + pgvector, Python 3, Nginx,
# clones the repo, seeds the database, and starts the FastAPI server.
#
# After running:
#   1. Edit /opt/wazi/.env with real secrets
#   2. Run: python /opt/wazi/scripts/seed_db.py
#   3. Verify: curl http://localhost:8000/health

set -e  # Exit on any error

echo "=== Wazi VPS Setup ==="
echo ""

# --- System update ---
echo "[1/8] Updating system packages..."
apt update -qq && apt upgrade -y -qq

# --- Swap file (2GB safety net for 1GB RAM VPS) ---
echo "[2/8] Creating 2GB swap file..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "  Swap file created."
else
    echo "  Swap file already exists — skipping."
fi

# --- PostgreSQL 16 + pgvector ---
echo "[3/8] Installing PostgreSQL 16 + pgvector..."
apt install -y -qq postgresql postgresql-16-pgvector

# Configure PostgreSQL for low RAM (1GB VPS)
PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
if [ -f "$PG_CONF" ]; then
    cp "$PG_CONF" "$PG_CONF.backup"
    sed -i "s/^#*shared_buffers.*/shared_buffers = 128MB/" "$PG_CONF"
    sed -i "s/^#*effective_cache_size.*/effective_cache_size = 256MB/" "$PG_CONF"
    sed -i "s/^#*maintenance_work_mem.*/maintenance_work_mem = 32MB/" "$PG_CONF"
    sed -i "s/^#*work_mem.*/work_mem = 4MB/" "$PG_CONF"
    sed -i "s/^#*max_connections.*/max_connections = 10/" "$PG_CONF"
    echo "  PostgreSQL memory tuned for 1GB RAM."
fi

systemctl restart postgresql
systemctl enable postgresql

# Create database and user
echo "[4/8] Creating database and user..."
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
sudo -u postgres psql -c "CREATE USER wazi WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || echo "  User 'wazi' already exists — skipping."
sudo -u postgres psql -c "CREATE DATABASE wazi_db OWNER wazi;" 2>/dev/null || echo "  Database 'wazi_db' already exists — skipping."
sudo -u postgres psql -d wazi_db -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null
echo "  DATABASE_URL=postgresql://wazi:${DB_PASSWORD}@localhost:5432/wazi_db"
echo "  ^ SAVE THIS LINE — you'll need it for .env"

# --- Python + dependencies ---
echo "[5/8] Installing Python and tools..."
apt install -y -qq python3-pip python3-venv python3-dev libpq-dev git nginx

# --- Clone repo ---
echo "[6/8] Cloning Wazi repository..."
if [ ! -d /opt/wazi ]; then
    git clone https://github.com/JoylynnWamjiru/Wazi-.git /opt/wazi
else
    cd /opt/wazi && git pull origin main
fi

cd /opt/wazi
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# --- .env template ---
echo "[7/8] Creating .env template..."
cat > /opt/wazi/.env << 'ENVEOF'
# Wazi — Environment Variables
# Fill in real values before starting the server.

DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

DATABASE_URL=postgresql://wazi:REPLACE_WITH_DB_PASSWORD@localhost:5432/wazi_db

AT_API_KEY=your-at-api-key
AT_USERNAME=sandbox
WA_BOT_NUMBER=+254700000000

ID_SALT=REPLACE_WITH_SECRETS_TOKEN_HEX_32_OUTPUT
ADMIN_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
ENVEOF

# Replace the DB password placeholder
sed -i "s/REPLACE_WITH_DB_PASSWORD/${DB_PASSWORD}/" /opt/wazi/.env

echo "  .env template created. Edit /opt/wazi/.env with real values."

# --- Nginx reverse proxy ---
echo "[8/8] Configuring Nginx..."
cat > /etc/nginx/sites-available/wazi << 'NGINXEOF'
server {
    listen 80;
    server_name 157.230.232.223;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/wazi /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# --- systemd service ---
cat > /etc/systemd/system/wazi.service << 'UNITEOF'
[Unit]
Description=Wazi FastAPI
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/wazi
Environment=PATH=/opt/wazi/venv/bin
ExecStart=/opt/wazi/venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable wazi

# --- Firewall ---
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/wazi/.env:"
echo "     - DEEPSEEK_API_KEY (your actual key)"
echo "     - ID_SALT (run: python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo "     - ADMIN_PASSWORD (strong password)"
echo ""
echo "  2. Seed the database:"
echo "     cd /opt/wazi && source venv/bin/activate"
echo "     python scripts/seed_db.py"
echo ""
echo "  3. Start Wazi:"
echo "     systemctl start wazi"
echo "     systemctl status wazi"
echo "     curl http://localhost:8000/health"
echo ""
echo "  4. Test from outside:"
echo "     curl http://157.230.232.223/health"
echo ""
echo "  DB Password (save this): ${DB_PASSWORD}"
