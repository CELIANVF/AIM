#!/usr/bin/env python3
"""Envoie un e-mail de test via Flask-Mail (variables MAIL_* du fichier `.env` à la racine du projet)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask
from flask_mail import Message

from config import Config
from mail import mail


def _print_smtp_combo_warnings() -> None:
    """Avertit si port / TLS / SSL sont incohérents (cause fréquente de connexion fermée, ex. Gmail)."""
    port = int(Config.MAIL_PORT or 0)
    tls = Config.MAIL_USE_TLS
    ssl = Config.MAIL_USE_SSL
    lines: list[str] = []
    if port == 465 and not ssl:
        lines.append(
            "• Port 465 sans MAIL_USE_SSL=true : le serveur ferme souvent la connexion tout de suite. "
            "Mettez MAIL_USE_SSL=true et MAIL_USE_TLS=false, ou passez au port 587 avec TLS."
        )
    if ssl and tls:
        lines.append(
            "• MAIL_USE_SSL et MAIL_USE_TLS activés en même temps : en général il faut l’un ou l’autre "
            "(465 + SSL seul, ou 587 + TLS seul)."
        )
    if port == 587 and ssl and not tls:
        lines.append(
            "• Port 587 avec SSL implicite est rare ; en général 587 utilise STARTTLS (MAIL_USE_TLS=true, "
            "MAIL_USE_SSL=false)."
        )
    for line in lines:
        print(line, file=sys.stderr)


def _print_smtp_troubleshooting() -> None:
    print(
        "\nPistes courantes pour « Connection unexpectedly closed » :\n"
        "  – Gmail : vérifier la combinaison port 587+TLS ou 465+SSL (voir `.env.example`).\n"
        "  – Mot de passe : utiliser un « mot de passe d’application » Google si la 2FA est active.\n"
        "  – Relancer avec --verbose pour afficher l’échange SMTP brut.\n",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Envoie un e-mail de test pour valider la configuration SMTP (AIM)."
    )
    parser.add_argument("to", help="Adresse e-mail du destinataire")
    parser.add_argument(
        "-s",
        "--subject",
        default="AIM — test d'envoi mail",
        help="Sujet du message",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Affiche l’échange SMTP (debug), même si MAIL_DEBUG n’est pas dans .env",
    )
    args = parser.parse_args()
    dest = args.to.strip()
    if not dest or "@" not in dest:
        print("Erreur : fournissez une adresse e-mail destinataire valide.", file=sys.stderr)
        return 1

    if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
        print(
            "Erreur : définissez MAIL_USERNAME et MAIL_PASSWORD dans `.env` (voir `.env.example`).",
            file=sys.stderr,
        )
        return 1

    sender = Config.MAIL_DEFAULT_SENDER or Config.MAIL_USERNAME
    if not sender:
        print("Erreur : définissez au minimum MAIL_DEFAULT_SENDER ou MAIL_USERNAME.", file=sys.stderr)
        return 1

    _print_smtp_combo_warnings()

    app = Flask(__name__)
    app.config.from_object(Config)
    if args.verbose:
        app.config["MAIL_DEBUG"] = 1
        print(
            f"SMTP : {Config.MAIL_SERVER!r} port={Config.MAIL_PORT} "
            f"TLS={Config.MAIL_USE_TLS} SSL={Config.MAIL_USE_SSL}",
            file=sys.stderr,
        )
    mail.init_app(app)

    body = (
        "Ceci est un message de test envoyé par le script scripts/send_test_mail.py.\n\n"
        "Si vous le recevez, la configuration SMTP (Flask-Mail) est correcte.\n"
    )

    with app.app_context():
        msg = Message(
            subject=args.subject,
            recipients=[dest],
            body=body,
            sender=sender,
        )
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Échec de l'envoi : {e}", file=sys.stderr)
            _print_smtp_troubleshooting()
            return 1

    print(f"E-mail envoyé à {dest!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
