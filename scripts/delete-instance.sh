#!/usr/bin/env bash
# Supprime une instance AIM (service, nginx, certificat, fichiers).
#
# Usage :
#   sudo bash scripts/delete-instance.sh --name testauto --domain testauto.aim.celian-vf.fr
#   sudo bash scripts/delete-instance.sh --name testauto --domain testauto.aim.celian-vf.fr --yes
#
# Options :
#   --name, -n       Nom du service systemd (ex. testauto)
#   --domain, -d     Domaine nginx / certbot (ex. testauto.aim.celian-vf.fr)
#   --dir            Répertoire de l'instance (défaut : /home/$USER/AIM-<name>)
#   --yes, -y        Ne pas demander de confirmation
#   --purge-cert     Supprimer aussi le certificat Let's Encrypt (sinon conservé pour la page 410)
#   --help, -h       Aide

set -euo pipefail

INSTANCE_NAME=""
DOMAIN=""
INSTANCE_DIR=""
ASSUME_YES=false
PURGE_CERT=false
RUN_USER="${SUDO_USER:-${USER:-celian}}"

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

service_exists() {
  [[ -f "/etc/systemd/system/${INSTANCE_NAME}.service" ]] \
    || systemctl cat "${INSTANCE_NAME}.service" &>/dev/null
}

install_gone_nginx() {
  local nginx_path="/etc/nginx/sites-available/${DOMAIN}"
  local cert_dir="/etc/letsencrypt/live/${DOMAIN}"

  {
    cat <<EOF
# Domaine AIM supprimé — 410 Gone (scripts/delete-instance.sh)
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    default_type text/plain;
    return 410 "Cette instance AIM a été supprimée.\n";
}
EOF
    local ssl_cert="" ssl_key=""
    if [[ -f "${cert_dir}/fullchain.pem" && -f "${cert_dir}/privkey.pem" ]]; then
      ssl_cert="${cert_dir}/fullchain.pem"
      ssl_key="${cert_dir}/privkey.pem"
    else
      # Certificat du domaine supprimé : repli pour éviter le proxy vers une autre instance AIM.
      for fallback in \
        "/etc/letsencrypt/live/aim.celian-vf.fr" \
        "/etc/letsencrypt/live/matos.anc93.com"; do
        if [[ -f "${fallback}/fullchain.pem" && -f "${fallback}/privkey.pem" ]]; then
          ssl_cert="${fallback}/fullchain.pem"
          ssl_key="${fallback}/privkey.pem"
          break
        fi
      done
    fi

    if [[ -n "$ssl_cert" ]]; then
      cat <<EOF

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN};

    ssl_certificate ${ssl_cert};
    ssl_certificate_key ${ssl_key};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    default_type text/plain;
    return 410 "Cette instance AIM a été supprimée.\n";
}
EOF
    fi
  } > "$nginx_path"

  ln -sf "$nginx_path" "/etc/nginx/sites-enabled/${DOMAIN}"
  echo "Nginx : page 410 installée pour ${DOMAIN} (plus de fallback vers une autre instance)."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|-n) INSTANCE_NAME="$2"; shift 2 ;;
    --domain|-d) DOMAIN="$2"; shift 2 ;;
    --dir) INSTANCE_DIR="$2"; shift 2 ;;
    --yes|-y) ASSUME_YES=true; shift ;;
    --purge-cert) PURGE_CERT=true; shift ;;
    --keep-cert) echo "Attention : --keep-cert est obsolète (certificat conservé par défaut)." >&2; shift ;;
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

if service_exists; then
  systemctl stop "$INSTANCE_NAME" 2>/dev/null || true
  systemctl disable "$INSTANCE_NAME" 2>/dev/null || true
  echo "Service ${INSTANCE_NAME} arrêté et désactivé."
else
  echo "Service ${INSTANCE_NAME} : déjà absent."
fi

if [[ -f "/etc/systemd/system/${INSTANCE_NAME}.service" ]]; then
  rm -f "/etc/systemd/system/${INSTANCE_NAME}.service"
  systemctl daemon-reload
  echo "Unité systemd supprimée."
fi

install_gone_nginx

if nginx -t; then
  systemctl reload nginx
  echo "Nginx rechargé."
else
  echo "Erreur : nginx -t a échoué — restauration manuelle requise." >&2
  exit 1
fi

if $PURGE_CERT && [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
  certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || {
    echo "Certbot delete a échoué pour ${DOMAIN}."
  }
  echo "Certificat Let's Encrypt supprimé."
elif [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
  echo "Certificat Let's Encrypt conservé (HTTPS 410 sur ${DOMAIN})."
fi

if [[ -d "$INSTANCE_DIR" ]]; then
  rm -rf "$INSTANCE_DIR"
  echo "Répertoire ${INSTANCE_DIR} supprimé."
else
  echo "Répertoire ${INSTANCE_DIR} : déjà absent."
fi

echo ""
echo "Instance ${DOMAIN} supprimée."
echo "Vérification : curl -sI https://${DOMAIN}/ | head -1  (attendu : HTTP/1.1 410 Gone)"
