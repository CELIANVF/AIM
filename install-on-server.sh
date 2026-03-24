#!/bin/bash
# Run this ON THE SERVER from the application directory (e.g. ~/AIM).
# It creates venv, installs deps, starts Gunicorn via systemd, and enables Nginx.
#
# Usage:
#   cd ~/AIM && chmod +x install-on-server.sh && ./install-on-server.sh matos.anc93.com
#   plusieurs noms (www + apex) :
#   ./install-on-server.sh matos.anc93.com www.matos.anc93.com
#   accès par IP uniquement (catch-all) :
#   ./install-on-server.sh _

set -euo pipefail

AIM_ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"

if [[ $# -gt 0 ]]; then
  SERVER_NAME="$*"
else
  SERVER_NAME="${SERVER_NAME:-_}"
fi

if [[ "$SERVER_NAME" == "_" ]]; then
  NGINX_SERVER_LINE="server_name _;"
else
  NGINX_SERVER_LINE="server_name ${SERVER_NAME};"
fi

echo "=========================================="
echo "AIM — installation sur le serveur"
echo "=========================================="
echo "Répertoire app : $AIM_ROOT"
echo "server_name Nginx : $SERVER_NAME"
echo "Utilisateur service : $SERVICE_USER"
echo ""

if [[ ! -f "$AIM_ROOT/app.py" ]]; then
  echo "Erreur : app.py introuvable dans $AIM_ROOT"
  exit 1
fi

cd "$AIM_ROOT"

echo "[1/6] Environnement Python…"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo "[2/6] Base de données (migrations Flask)…"
export FLASK_APP=app.py
if [[ -d migrations ]]; then
  flask db upgrade || echo "Note : flask db upgrade a échoué (première install ? vérifiez les logs)."
fi

echo "[3/6] Service systemd (Gunicorn)…"
sudo tee "/etc/systemd/system/aim.service" > /dev/null << SERVICE
[Unit]
Description=AIM (Gunicorn)
After=network.target

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${AIM_ROOT}
Environment=FLASK_DEBUG=0
# Port 5001: évite le conflit avec le serveur de dev Flask (5000) si encore lancé
ExecStart=${AIM_ROOT}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5001 --timeout 120 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable aim
sudo systemctl restart aim

echo "[4/6] Configuration Nginx…"
sudo tee /etc/nginx/sites-available/aim > /dev/null << NGINX
server {
    listen 80;
    listen [::]:80;
    ${NGINX_SERVER_LINE}

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias ${AIM_ROOT}/static/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location ~ /\. {
        deny all;
    }
}
NGINX

if [[ -L /etc/nginx/sites-enabled/default ]] || [[ -f /etc/nginx/sites-enabled/default ]]; then
  echo "       Désactivation du site Nginx par défaut (conflit port 80)…"
  sudo rm -f /etc/nginx/sites-enabled/default
fi

sudo ln -sf /etc/nginx/sites-available/aim /etc/nginx/sites-enabled/aim
sudo nginx -t
# start (not only reload): reload fails if nginx was never started
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "[5/6] Pare-feu (si ufw est actif)…"
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  echo "       Ports 80/443 autorisés dans ufw."
else
  echo "       ufw inactif ou absent — rien à changer (ports souvent déjà ouverts)."
fi

echo "[6/6] Vérification…"
sleep 1
sudo systemctl --no-pager status aim || true

echo ""
echo "=========================================="
echo "Terminé."
echo "=========================================="
echo "Test local sur le serveur : curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5001/"
echo "Test via Nginx : curl -s -o /dev/null -w '%{http_code}' -H 'Host: ${SERVER_NAME}' http://127.0.0.1/"
echo ""
echo "Commandes utiles :"
echo "  sudo journalctl -u aim -f"
echo "  sudo systemctl restart aim"
echo "HTTPS : sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d VOTRE_DOMAINE"
echo ""
if [[ "$SERVER_NAME" != "_" ]]; then
  FIRST_DOMAIN="${SERVER_NAME%% *}"
  echo "Si le domaine ne répond pas depuis Internet :"
  echo "  1) DNS : dig +short A ${FIRST_DOMAIN}  → doit être l’IP publique de ce VPS"
  echo "  2) server_name Nginx doit inclure ce domaine : ./install-on-server.sh ${FIRST_DOMAIN}"
  echo "  3) Pare-feu / hébergeur : ports 80 et 443 ouverts vers cette machine"
  echo ""
fi
