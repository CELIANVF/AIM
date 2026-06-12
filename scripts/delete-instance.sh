#!/usr/bin/env bash
# Supprime une instance AIM (service, nginx, certificat, fichiers).
#
# Usage :
#   sudo bash scripts/delete-instance.sh --name testauto --domain testauto.aim.celian-vf.fr
#   sudo bash scripts/delete-instance.sh --name testauto --domain testauto.aim.celian-vf.fr --yes
#
# Options :
#   --name, -n     Nom du service systemd (ex. testauto)
#   --domain, -d   Domaine nginx / certbot (ex. testauto.aim.celian-vf.fr)
#   --dir          Répertoire de l'instance (défaut : /home/$USER/AIM-<name>)
#   --yes, -y      Ne pas demander de confirmation
#   --keep-cert    Garder le certificat Let's Encrypt
#   --help, -h     Aide

set -euo pipefail

INSTANCE_NAME=""
DOMAIN=""
INSTANCE_DIR=""
ASSUME_YES=false
KEEP_CERT=false
RUN_USER="${SUDO_USER:-${USER:-celian}}"

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|-n) INSTANCE_NAME="$2"; shift 2 ;;
    --domain|-d) DOMAIN="$2"; shift 2 ;;
    --dir) INSTANCE_DIR="$2"; shift 2 ;;
    --yes|-y) ASSUME_YES=true; shift ;;
    --keep-cert) KEEP_CERT=true; shift ;;
    --help|-h) usage 0 ;;
    *) echo "Option inconnue : $1" >&2; usage 1 ;;
  esac
done

[[ -n "$INSTANCE_NAME" ]] || { echo "Erreur : --name requis." >&2; usage 1; }
[[ -n "$DOMAIN" ]] || { echo "Erreur : --domain requis." >&2; usage 1; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ce script doit être lancé avec sudo." >&2
  echo "  sudo bash scripts/delete-instance.sh --name ${INSTANCE_NAME} --domain ${DOMAIN}"
  exit 1
fi

INSTANCE_DIR="${INSTANCE_DIR:-/home/${RUN_USER}/AIM-${INSTANCE_NAME}}"

echo "Instance à supprimer :"
echo "  Nom service : ${INSTANCE_NAME}"
echo "  Domaine     : ${DOMAIN}"
echo "  Répertoire  : ${INSTANCE_DIR}"
echo ""

if ! $ASSUME_YES; then
  read -r -p "Confirmer la suppression ? [oui/N] " confirm
  if [[ "${confirm,,}" != "oui" && "${confirm,,}" != "o" && "${confirm,,}" != "yes" ]]; then
    echo "Annulé."
    exit 0
  fi
fi

if systemctl list-unit-files "${INSTANCE_NAME}.service" &>/dev/null; then
  systemctl stop "$INSTANCE_NAME" 2>/dev/null || true
  systemctl disable "$INSTANCE_NAME" 2>/dev/null || true
  echo "Service ${INSTANCE_NAME} arrêté et désactivé."
fi

if [[ -f "/etc/systemd/system/${INSTANCE_NAME}.service" ]]; then
  rm -f "/etc/systemd/system/${INSTANCE_NAME}.service"
  systemctl daemon-reload
  echo "Unité systemd supprimée."
fi

if [[ -L "/etc/nginx/sites-enabled/${DOMAIN}" || -f "/etc/nginx/sites-enabled/${DOMAIN}" ]]; then
  rm -f "/etc/nginx/sites-enabled/${DOMAIN}"
  echo "Lien nginx sites-enabled supprimé."
fi

if [[ -f "/etc/nginx/sites-available/${DOMAIN}" ]]; then
  rm -f "/etc/nginx/sites-available/${DOMAIN}"
  echo "Config nginx sites-available supprimée."
fi

if nginx -t 2>/dev/null; then
  systemctl reload nginx
  echo "Nginx rechargé."
else
  echo "Attention : nginx -t a échoué — vérifiez la config manuellement." >&2
fi

if ! $KEEP_CERT && [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
  certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || {
    echo "Certbot delete a échoué — certificat peut-être déjà absent."
  }
  echo "Certificat Let's Encrypt supprimé (si présent)."
fi

if [[ -d "$INSTANCE_DIR" ]]; then
  rm -rf "$INSTANCE_DIR"
  echo "Répertoire ${INSTANCE_DIR} supprimé."
else
  echo "Répertoire ${INSTANCE_DIR} absent — rien à supprimer."
fi

echo ""
echo "Instance ${DOMAIN} supprimée."
