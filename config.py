import os

# Base SQLite toujours au même endroit (évite une base vide si le CWD n’est pas la racine du projet).
_basedir = os.path.abspath(os.path.dirname(__file__))
_instance_dir = os.path.join(_basedir, 'instance')
os.makedirs(_instance_dir, exist_ok=True)
_sqlite_path = os.path.join(_instance_dir, 'equipment.db').replace("\\", "/")


class Config:
    SECRET_KEY = 'your-secret-key-here'
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + _sqlite_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False