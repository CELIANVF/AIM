"""Email utilities for AIM application using Flask-Mail."""

from flask_mail import Mail, Message
from flask import render_template, url_for
import secrets

mail = Mail()


def generate_temporary_password(length=12):
    """
    Generate a secure random temporary password.

    Args:
        length: Length of the password (default 12 characters)

    Returns:
        A secure random password with mixed case letters and digits
    """
    # Use secrets for cryptographically secure random generation
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_archer_credentials(archer, temporary_password):
    """
    Send an email to an Archer with their login credentials.

    Args:
        archer: Archer object with email attribute
        temporary_password: The generated temporary password

    Returns:
        True if email was sent successfully, False otherwise
    """
    from app import app

    if not archer.email:
        app.logger.warning(f"Cannot send credentials to archer {archer.id}: no email address")
        return False

    try:
        # Build the email content
        login_url = url_for('login', _external=True)

        subject = "Vos identifiants de connexion - ANC93"

        # Render HTML template if available, otherwise use plain text
        try:
            html_body = render_template(
                'emails/archer_credentials.html',
                archer=archer,
                temporary_password=temporary_password,
                login_url=login_url
            )
        except Exception:
            html_body = None

        body = f"""Bonjour {archer.first_name or archer.last_name or 'Archers'},

Votre compte archer a été créé sur la plateforme AIM de l'ANC93.

Voici vos identifiants de connexion :

Email: {archer.email}
Mot de passe temporaire: {temporary_password}

Pour vous connecter, rendez-vous sur : {login_url}

IMPORTANT:
- Ce mot de passe est temporaire. Nous vous recommandons de le changer dès votre première connexion.
- Ne partagez jamais vos identifiants avec quiconque.

Cordialement,
L'équipe ANC93
"""

        msg = Message(
            subject=subject,
            recipients=[archer.email],
            body=body,
            html=html_body
        )

        mail.send(msg)
        app.logger.info(f"Credentials email sent to {archer.email}")
        return True

    except Exception as e:
        app.logger.error(f"Failed to send credentials email to {archer.email}: {str(e)}")
        return False
