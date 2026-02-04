#!/usr/bin/env python
"""Script pour créer un utilisateur administrateur."""

import sys
from app import app, db
from models import User

def create_user(username, password):
    """Créer un nouvel utilisateur."""
    with app.app_context():
        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"L'utilisateur '{username}' existe déjà.")
            return False
        
        # Créer le nouvel utilisateur
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Utilisateur '{username}' créé avec succès!")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python create_user.py <username> <password>")
        print("Exemple: python create_user.py admin monmotdepasse123")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    create_user(username, password)
