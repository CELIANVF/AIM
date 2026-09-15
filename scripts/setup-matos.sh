#!/usr/bin/env bash
# Installation systemd + nginx pour l'instance principale sur matos (/root/AIM).
#
# Usage (sur matos, en root) :
#   sudo bash scripts/setup-matos.sh
#
# Prérequis : dépôt cloné dans /root/AIM, venv créé, .env configuré.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTANCE_DIR="/root/AIM"
SERVICE_NAME="aim"
DOMAIN="matos.anc93.com"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Exécutez avec sudo." >&2
  exit 1
fi

echo "Installation des paquets système (git, nginx, python3)…"
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  git nginx python3 python3-venv python3-pip

if [[ "$ROOT" != "$INSTANCE_DIR" ]]; then
  echo "Attention : ce script est prévu pour ${INSTANCE_DIR} (cwd: ${ROOT})." >&2
fi

if [[ ! -d "${INSTANCE_DIR}/venv" ]]; then
  echo "Erreur : ${INSTANCE_DIR}/venv absent." >&2
  exit 1
fi

cp "${INSTANCE_DIR}/deploy/instances/aim-matos/aim.service" "/etc/systemd/system/${SERVICE_NAME}.service"
cp "${INSTANCE_DIR}/deploy/instances/aim-matos/nginx.conf" "/etc/nginx/sites-available/${DOMAIN}"

ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

nginx -t
systemctl reload nginx

if [[ ! -f "${INSTANCE_DIR}/.deploy.local" ]]; then
  cp "${INSTANCE_DIR}/.deploy.local.example" "${INSTANCE_DIR}/.deploy.local"
  echo "Fichier .deploy.local créé (AIM_SERVICE=${SERVICE_NAME})."
fi

echo ""
echo "Instance matos prête."
echo "  Service : systemctl status ${SERVICE_NAME}"
echo "  URL     : http://${DOMAIN}/"
echo "  SSL     : certbot --nginx -d ${DOMAIN}"
