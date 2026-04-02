import os

from dotenv import load_dotenv

# Charge `.env` à la racine du projet (ignoré par git) pour le dev / déploiement local.
_basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(_basedir, '.env'))

# Base SQLite toujours au même endroit (évite une base vide si le CWD n’est pas la racine du projet).
_instance_dir = os.path.join(_basedir, 'instance')
os.makedirs(_instance_dir, exist_ok=True)
_sqlite_path = os.path.join(_instance_dir, 'equipment.db').replace("\\", "/")


def _env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None or v.strip() == '':
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default):
    v = os.environ.get(name)
    if v is None or str(v).strip() == '':
        return default
    try:
        return int(v)
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-to-a-random-secret-key'
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + _sqlite_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail — définir dans `.env` (voir `.env.example`)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = _env_int('MAIL_PORT', 587)
    MAIL_USE_TLS = _env_bool('MAIL_USE_TLS', True)
    MAIL_USE_SSL = _env_bool('MAIL_USE_SSL', False)
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or None
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or None
    # 0/1 pour Flask-Mail (journal SMTP sur stderr, utile avec scripts/send_test_mail.py --verbose)
    MAIL_DEBUG = int(_env_bool('MAIL_DEBUG', False))