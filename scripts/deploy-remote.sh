#!/usr/bin/env bash
# À exécuter sur le serveur (répertoire du dépôt cloné).
# Utilisé par la CI après un push sur main, ou manuellement : ./scripts/deploy-remote.sh
#
# Surcharges optionnelles (fichier non versionné à la racine du dépôt) :
#   .deploy.local — AIM_SERVICE, VENV_DIR, RELOAD_NGINX=1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .deploy.local ]]; then
  # shellcheck source=/dev/null
  source .deploy.local
fi

VENV_DIR="${VENV_DIR:-venv}"
if [[ ! -d "$VENV_DIR" && -d .venv ]]; then
  VENV_DIR=.venv
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Erreur : environnement virtuel absent (${VENV_DIR})." >&2
  echo "Créez-le : python3 -m venv ${VENV_DIR} && source ${VENV_DIR}/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

AIM_SERVICE="${AIM_SERVICE:-aim}"

if [[ "$(id -u)" -eq 0 ]]; then
  SYSTEMCTL=(systemctl)
else
  SYSTEMCTL=(sudo systemctl)
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
export FLASK_APP=app.py

python scripts/backup_database.py

git fetch origin
git checkout main
git reset --hard origin/main

pip install -r requirements.txt

if [[ -d migrations ]]; then
  flask db upgrade || echo "Attention : flask db upgrade a échoué (voir les logs)."
fi

if [[ -f "/etc/systemd/system/${AIM_SERVICE}.service" ]] \
    || "${SYSTEMCTL[@]}" cat "${AIM_SERVICE}.service" &>/dev/null; then
  "${SYSTEMCTL[@]}" restart "${AIM_SERVICE}"
  echo "Service ${AIM_SERVICE} redémarré."
else
  echo "Attention : service systemd « ${AIM_SERVICE} » introuvable — pas de restart." >&2
fi

if [[ "${RELOAD_NGINX:-0}" == "1" ]] && command -v nginx >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    nginx -t && systemctl reload nginx
  else
    sudo nginx -t && sudo systemctl reload nginx
  fi
  echo "Nginx rechargé."
fi

echo "Déploiement OK — $(git rev-parse --short HEAD) ($(date -Iseconds))"
