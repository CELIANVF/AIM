#!/usr/bin/env bash
# Crée rapidement une nouvelle instance AIM sur le serveur.
#
# Usage (sur le VPS) — TOUJOURS dans cet ordre :
#   1. bash scripts/create-instance.sh --name mon-club --domain matos.monclub.fr
#   2. sudo bash scripts/create-instance.sh --name mon-club --domain matos.monclub.fr --sudo
#
# La phase --sudo configure nginx/systemd uniquement ; elle ne clone pas le code ni le venv.
#
# Options :
#   --name, -n       Identifiant (service systemd, dossier deploy/instances/)
#   --domain, -d     Nom de domaine (nginx + certbot)
#   --port, -p       Port Gunicorn (défaut : premier libre entre 5001–5099)
#   --dir            Répertoire de l'instance (défaut : /home/$USER/AIM-<name>)
#   --source-env     .env dont copier uniquement les variables MAIL_* (défaut : /home/$USER/AIM/.env)
#   --git-url        Dépôt à cloner (défaut : origin du dépôt courant)
#   --cert-email     E-mail Let's Encrypt (défaut : celian@celian-vf.fr)
#   --admin-password Mot de passe admin (défaut : généré aléatoirement)
#   --sudo           Phase systemd + nginx + certbot (nécessite root)
#   --help, -h       Aide
#
# Suppression : scripts/delete-instance.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES_DIR="$ROOT/deploy/templates"

INSTANCE_NAME=""
DOMAIN=""
GUNICORN_PORT=""
INSTANCE_DIR=""
SOURCE_ENV=""
GIT_URL=""
CERT_EMAIL="${AIM_CERT_EMAIL:-celian@celian-vf.fr}"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD=""
ADMIN_CREATED=false
DO_SUDO=false
RUN_USER="${SUDO_USER:-${USER:-celian}}"

ADMIN_CREDENTIALS_FILE=""

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

slug_ok() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$ ]]
}

domain_ok() {
  [[ "$1" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]
}

render_template() {
  local template="$1" dest="$2"
  sed \
    -e "s|{{INSTANCE_NAME}}|${INSTANCE_NAME}|g" \
    -e "s|{{INSTANCE_DIR}}|${INSTANCE_DIR}|g" \
    -e "s|{{GUNICORN_PORT}}|${GUNICORN_PORT}|g" \
    -e "s|{{DOMAIN}}|${DOMAIN}|g" \
    -e "s|{{USER}}|${RUN_USER}|g" \
    -e "s|{{GROUP}}|${RUN_USER}|g" \
    "$template" > "$dest"
}

pick_free_port() {
  local p
  for p in $(seq 5001 5099); do
    if ! ss -tln 2>/dev/null | grep -q "127.0.0.1:${p} "; then
      echo "$p"
      return 0
    fi
  done
  echo "Erreur : aucun port libre entre 5001 et 5099." >&2
  exit 1
}

default_git_url() {
  if git -C "$ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
    git -C "$ROOT" remote get-url origin 2>/dev/null || true
  fi
}

instance_database_url() {
  local db_file="${INSTANCE_DIR}/instance/equipment.db"
  echo "sqlite:///${db_file}"
}

init_instance_env() {
  local env_file="${INSTANCE_DIR}/.env"
  local db_url
  db_url="$(instance_database_url)"
  local secret_key
  secret_key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

  if [[ -f "$env_file" ]]; then
    echo ".env déjà présent — non modifié."
    if ! grep -q '^DATABASE_URL=' "$env_file"; then
      tail -c1 "$env_file" | read -r _ || echo >> "$env_file"
      echo "DATABASE_URL=${db_url}" >> "$env_file"
      echo "DATABASE_URL ajouté (base locale de cette instance)."
    fi
    return
  fi

  mkdir -p "${INSTANCE_DIR}/instance"

  {
    echo "# Instance AIM : ${INSTANCE_NAME} (${DOMAIN})"
    echo "# Généré par scripts/create-instance.sh — ne pas réutiliser sur une autre instance."
    echo ""
    if [[ -f "$SOURCE_ENV" ]]; then
      echo "# SMTP (copié depuis ${SOURCE_ENV})"
      grep -E '^MAIL_' "$SOURCE_ENV" 2>/dev/null || true
      echo ""
    else
      echo "# SMTP — renseigner (voir .env.example)"
      grep -E '^MAIL_' "${INSTANCE_DIR}/.env.example" 2>/dev/null || true
      echo ""
    fi
    echo "# Base de données propre à cette instance"
    echo "DATABASE_URL=${db_url}"
    echo ""
    echo "# Clé secrète propre à cette instance"
    echo "SECRET_KEY=${secret_key}"
  } > "$env_file"

  echo ".env créé : DATABASE_URL → ${INSTANCE_DIR}/instance/equipment.db"
}

save_admin_credentials() {
  ADMIN_CREDENTIALS_FILE="${INSTANCE_DIR}/instance/.initial-admin-credentials"
  mkdir -p "${INSTANCE_DIR}/instance"
  cat > "$ADMIN_CREDENTIALS_FILE" <<EOF
# Identifiants admin initiaux — généré par scripts/create-instance.sh
# Conserver en lieu sûr ; supprimé avec l'instance (scripts/delete-instance.sh).
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
DOMAIN=${DOMAIN}
CREATED_AT=$(date -Iseconds)
EOF
  chmod 600 "$ADMIN_CREDENTIALS_FILE"
}

load_admin_credentials() {
  ADMIN_CREDENTIALS_FILE="${INSTANCE_DIR}/instance/.initial-admin-credentials"
  if [[ ! -f "$ADMIN_CREDENTIALS_FILE" ]]; then
    return 1
  fi
  # shellcheck source=/dev/null
  source "$ADMIN_CREDENTIALS_FILE"
  return 0
}

ensure_admin_user() {
  cd "$INSTANCE_DIR"
  # shellcheck source=/dev/null
  source venv/bin/activate
  export FLASK_APP=app.py

  if python3 -c "
from app import app
from models import db, User
with app.app_context():
    print('admin_exists' if User.query.filter_by(username='${ADMIN_USERNAME}').first() else 'no_admin')
" | grep -q admin_exists; then
    echo "Compte admin « ${ADMIN_USERNAME} » déjà présent."
    if load_admin_credentials; then
      ADMIN_CREATED=false
      return 0
    fi
    echo "Mot de passe inconnu — utilisez : flask reset-admin-password -u ${ADMIN_USERNAME}"
    return 0
  fi

  ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')}"
  python3 -c "
from app import app
from models import db, User
with app.app_context():
    u = User(username='${ADMIN_USERNAME}', role='admin')
    u.set_password('${ADMIN_PASSWORD}')
    db.session.add(u)
    db.session.commit()
"
  ADMIN_CREATED=true
  save_admin_credentials
  echo "Compte admin « ${ADMIN_USERNAME} » créé."
}

print_final_summary() {
  local phase="${1:-}"
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  Instance AIM : ${DOMAIN}"
  [[ -n "$phase" ]] && echo "  Phase        : ${phase}"
  echo "════════════════════════════════════════════════════════"
  echo "  URL          : https://${DOMAIN}"
  echo "  Répertoire   : ${INSTANCE_DIR}"
  echo "  Service      : ${INSTANCE_NAME}"
  echo "  Port         : ${GUNICORN_PORT}"
  echo "  Base         : ${INSTANCE_DIR}/instance/equipment.db"
  echo "────────────────────────────────────────────────────────"
  if load_admin_credentials 2>/dev/null; then
    echo "  Connexion admin :"
    echo "    Identifiant : ${ADMIN_USERNAME}"
    echo "    Mot de passe: ${ADMIN_PASSWORD}"
    echo "  (sauvegardé dans ${ADMIN_CREDENTIALS_FILE})"
  else
    echo "  Connexion admin : compte « ${ADMIN_USERNAME} » — mot de passe non disponible"
    echo "    Réinitialiser : cd ${INSTANCE_DIR} && source venv/bin/activate && flask reset-admin-password"
  fi
  echo "════════════════════════════════════════════════════════"
  if [[ "$phase" != "sudo" ]]; then
    echo ""
    echo "Étape suivante (sudo) :"
    echo "  sudo bash ${INSTANCE_DIR}/scripts/create-instance.sh \\"
    echo "    --name ${INSTANCE_NAME} --domain ${DOMAIN} --port ${GUNICORN_PORT} --sudo"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|-n) INSTANCE_NAME="$2"; shift 2 ;;
    --domain|-d) DOMAIN="$2"; shift 2 ;;
    --port|-p) GUNICORN_PORT="$2"; shift 2 ;;
    --dir) INSTANCE_DIR="$2"; shift 2 ;;
    --source-env) SOURCE_ENV="$2"; shift 2 ;;
    --git-url) GIT_URL="$2"; shift 2 ;;
    --cert-email) CERT_EMAIL="$2"; shift 2 ;;
    --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
    --sudo) DO_SUDO=true; shift ;;
    --help|-h) usage 0 ;;
    *) echo "Option inconnue : $1" >&2; usage 1 ;;
  esac
done

[[ -n "$INSTANCE_NAME" ]] || { echo "Erreur : --name requis." >&2; usage 1; }
[[ -n "$DOMAIN" ]] || { echo "Erreur : --domain requis." >&2; usage 1; }
slug_ok "$INSTANCE_NAME" || { echo "Erreur : --name invalide (a-z, 0-9, tirets)." >&2; exit 1; }
domain_ok "$DOMAIN" || { echo "Erreur : --domain invalide." >&2; exit 1; }

INSTANCE_DIR="${INSTANCE_DIR:-/home/${RUN_USER}/AIM-${INSTANCE_NAME}}"
GUNICORN_PORT="${GUNICORN_PORT:-$(pick_free_port)}"
GIT_URL="${GIT_URL:-$(default_git_url)}"
GIT_URL="${GIT_URL:-https://github.com/CELIANVF/AIM}"
SOURCE_ENV="${SOURCE_ENV:-/home/${RUN_USER}/AIM/.env}"

DEPLOY_INSTANCE_DIR="${INSTANCE_DIR}/deploy/instances/${INSTANCE_NAME}"
SERVICE_FILE="${DEPLOY_INSTANCE_DIR}/${INSTANCE_NAME}.service"
NGINX_FILE="${DEPLOY_INSTANCE_DIR}/${DOMAIN}.nginx.conf"

generate_deploy_files() {
  mkdir -p "$DEPLOY_INSTANCE_DIR"
  render_template "$TEMPLATES_DIR/instance.service.template" "$SERVICE_FILE"
  render_template "$TEMPLATES_DIR/instance.nginx.template" "$NGINX_FILE"
}

instance_is_provisioned() {
  [[ -f "${INSTANCE_DIR}/app.py" && -x "${INSTANCE_DIR}/venv/bin/gunicorn" ]]
}

provision_as_app_user() {
  local provision_args=(
    --name "$INSTANCE_NAME"
    --domain "$DOMAIN"
    --port "$GUNICORN_PORT"
    --dir "$INSTANCE_DIR"
  )
  [[ -n "$SOURCE_ENV" ]] && provision_args+=(--source-env "$SOURCE_ENV")
  [[ -n "$ADMIN_PASSWORD" ]] && provision_args+=(--admin-password "$ADMIN_PASSWORD")
  [[ -n "$GIT_URL" ]] && provision_args+=(--git-url "$GIT_URL")

  echo "Installation applicative (clone, venv, BDD) pour ${DOMAIN}..."
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "$RUN_USER" bash "$ROOT/scripts/create-instance.sh" "${provision_args[@]}"
  else
    bash "$ROOT/scripts/create-instance.sh" "${provision_args[@]}"
  fi
}

phase_sudo() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Relancez avec sudo : sudo bash $0 --name ${INSTANCE_NAME} --domain ${DOMAIN} --port ${GUNICORN_PORT} --sudo"
    exit 1
  fi

  if ! instance_is_provisioned; then
    if [[ -d "$INSTANCE_DIR" && ! -f "${INSTANCE_DIR}/app.py" ]]; then
      echo "Erreur : ${INSTANCE_DIR} existe mais l'application n'y est pas installée." >&2
      echo "Souvent causé par un --sudo lancé avant l'étape sans sudo." >&2
      echo "Corrigez avec :" >&2
      echo "  sudo rm -rf ${INSTANCE_DIR}" >&2
      echo "  bash scripts/create-instance.sh --name ${INSTANCE_NAME} --domain ${DOMAIN} --port ${GUNICORN_PORT}" >&2
      echo "  sudo bash scripts/create-instance.sh --name ${INSTANCE_NAME} --domain ${DOMAIN} --port ${GUNICORN_PORT} --sudo" >&2
      exit 1
    fi
    provision_as_app_user
  fi

  if [[ ! -f "$SERVICE_FILE" || ! -f "$NGINX_FILE" ]]; then
    echo "Erreur : fichiers deploy manquants dans ${DEPLOY_INSTANCE_DIR}." >&2
    echo "Relancez sans sudo : bash scripts/create-instance.sh --name ${INSTANCE_NAME} --domain ${DOMAIN} --port ${GUNICORN_PORT}" >&2
    exit 1
  fi

  chown -R "${RUN_USER}:${RUN_USER}" "$INSTANCE_DIR"

  cp "$SERVICE_FILE" "/etc/systemd/system/${INSTANCE_NAME}.service"
  systemctl daemon-reload
  systemctl enable "$INSTANCE_NAME"
  systemctl restart "$INSTANCE_NAME"
  sleep 1
  if ! systemctl is-active --quiet "$INSTANCE_NAME"; then
    echo "Erreur : le service ${INSTANCE_NAME} n'a pas démarré." >&2
    journalctl -u "$INSTANCE_NAME" -n 15 --no-pager >&2 || true
    exit 1
  fi
  echo "Service ${INSTANCE_NAME} démarré (127.0.0.1:${GUNICORN_PORT})."

  cp "$NGINX_FILE" "/etc/nginx/sites-available/${DOMAIN}"
  ln -sf "/etc/nginx/sites-available/${DOMAIN}" /etc/nginx/sites-enabled/
  nginx -t
  systemctl reload nginx
  echo "Nginx configuré pour ${DOMAIN}."

  if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL" || {
      echo "Certbot a échoué — lancez : certbot --nginx -d ${DOMAIN}"
    }
  else
    echo "Certificat SSL déjà présent pour ${DOMAIN}."
  fi

  print_final_summary "sudo"
  exit 0
}

if $DO_SUDO; then
  phase_sudo
fi

echo "=== Nouvelle instance AIM : ${DOMAIN} ==="
echo "  Nom service : ${INSTANCE_NAME}"
echo "  Répertoire  : ${INSTANCE_DIR}"
echo "  Port        : ${GUNICORN_PORT}"
echo ""

if [[ ! -d "$INSTANCE_DIR" ]]; then
  echo "Clonage de ${GIT_URL}..."
  git clone "$GIT_URL" "$INSTANCE_DIR"
fi

# S'assurer que les templates et ce script existent dans la copie clonée.
mkdir -p "$INSTANCE_DIR/deploy/templates" "$INSTANCE_DIR/scripts"
cp "$TEMPLATES_DIR/instance.service.template" "$INSTANCE_DIR/deploy/templates/"
cp "$TEMPLATES_DIR/instance.nginx.template" "$INSTANCE_DIR/deploy/templates/"
cp "$ROOT/scripts/create-instance.sh" "$ROOT/scripts/delete-instance.sh" "$INSTANCE_DIR/scripts/"
chmod +x "$INSTANCE_DIR/scripts/create-instance.sh" "$INSTANCE_DIR/scripts/delete-instance.sh"
generate_deploy_files

cd "$INSTANCE_DIR"

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate
pip install -q -r requirements.txt

init_instance_env

export FLASK_APP=app.py
if [[ -d migrations ]]; then
  flask db upgrade
fi

ensure_admin_user

print_final_summary "provision"
