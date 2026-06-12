"""Production configuration for AIM application"""
import os
from config import Config

class ProductionConfig(Config):
    # Security settings
    DEBUG = False
    TESTING = False
    
    # Database - use PostgreSQL for production (recommended)
    # Uncomment the line below and install psycopg2: pip install psycopg2-binary
    # SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/aim_db'
    
    # For SQLite (if staying with SQLite in production) — chemin relatif au dépôt de l'instance.
    _basedir = os.path.abspath(os.path.dirname(__file__))
    _default_sqlite = os.path.join(_basedir, 'instance', 'equipment.db').replace('\\', '/')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or ('sqlite:///' + _default_sqlite)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Use a strong secret key from environment variable
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-to-a-random-secret-key'
    
    # Session security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Logging
    LOG_TO_STDOUT = True
