#!/usr/bin/env bash
# À exécuter sur le serveur (répertoire du dépôt cloné).
# Utilisé par la CI après un push sur main, ou manuellement : ./scripts/deploy-remote.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d venv ]]; then
  echo "Erreur : venv absent. Créez-le avec : python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck source=/dev/null
source venv/bin/activate
export FLASK_APP=app.py

# Sauvegarde BDD avant mise à jour du code / migrations (voir scripts/backup_database.py)
python scripts/backup_database.py

git fetch origin
git checkout main
git reset --hard origin/main

pip install -r requirements.txt

if [[ -d migrations ]]; then
  flask db upgrade || echo "Attention : flask db upgrade a échoué (voir les logs)."
fi

sudo systemctl restart aim

echo "Déploiement OK — $(git rev-parse --short HEAD) ($(date -Iseconds))"
