#!/usr/bin/env bash
# Raccourci — instance aim.celian-vf.fr (voir scripts/create-instance.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/scripts/create-instance.sh" \
  --name aim-celian-vf \
  --domain aim.celian-vf.fr \
  --port 5002 \
  --dir /home/celian/AIM-celian-vf \
  "$@"
