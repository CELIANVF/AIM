#!/usr/bin/env python3
"""Sauvegarde la base avant déploiement (SQLite ou PostgreSQL).

Lit DATABASE_URL depuis l'environnement ou `.env` à la racine du dépôt.
Les fichiers vont dans instance/backups/ (déjà couvert par .gitignore via instance/).
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_file() -> None:
    p = ROOT / ".env"
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def resolve_sqlite_path(url: str) -> Path | None:
    from sqlalchemy.engine.url import make_url

    u = make_url(url)
    if not u.database or u.database == ":memory:":
        return None
    db = Path(u.database)
    if not db.is_absolute():
        db = ROOT / db
    return db


def main() -> int:
    load_dotenv_file()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = ROOT / "instance" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    url = (os.environ.get("DATABASE_URL") or "").strip()
    sqlite_default = ROOT / "instance" / "equipment.db"

    if not url:
        if not sqlite_default.is_file():
            print(
                "backup-database: pas de DATABASE_URL et pas de instance/equipment.db — rien à sauvegarder.",
                file=sys.stderr,
            )
            return 0
        dest = backup_dir / f"equipment-predeploy-{ts}.db"
        shutil.copy2(sqlite_default, dest)
        print(f"backup-database: copie SQLite → {dest}")
        return 0

    if url.startswith("sqlite:"):
        path = resolve_sqlite_path(url)
        if path is None or not path.is_file():
            print(f"backup-database: fichier SQLite introuvable ({path})", file=sys.stderr)
            return 1
        dest = backup_dir / f"equipment-predeploy-{ts}.db"
        shutil.copy2(path, dest)
        print(f"backup-database: copie SQLite → {dest}")
        return 0

    if url.startswith(("postgresql:", "postgres:")):
        dest = backup_dir / f"pg-predeploy-{ts}.sql.gz"
        r = subprocess.run(
            ["pg_dump", "--no-owner", "--no-acl", url],
            capture_output=True,
        )
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            print(f"backup-database: pg_dump a échoué:\n{err}", file=sys.stderr)
            return 1
        with gzip.open(dest, "wb") as f:
            f.write(r.stdout)
        print(f"backup-database: dump PostgreSQL → {dest}")
        return 0

    print(
        "backup-database: DATABASE_URL non géré pour une sauvegarde automatique "
        f"(préfixe: {url.split(':', 1)[0]}). Ajoutez une étape manuelle ou étendez scripts/backup_database.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
