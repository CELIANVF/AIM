# Application de Gestion du Matériel du Club de Tir à l'Arc

Cette application web permet de gérer le matériel du club de tir à l'arc, incluant les produits unitaires, les arcs composés, et les assignations aux archers.

## Installation

1. Assurez-vous d'avoir Python 3.8+ installé.
2. Clonez ou téléchargez le projet.
3. Créez un environnement virtuel : `python -m venv .venv`
4. Activez l'environnement : `.venv\Scripts\activate` (Windows)
5. Installez les dépendances : `pip install -r requirements.txt`
6. Initialisez la base de données : `flask db upgrade`
7. Lancez l'application : `flask run`

L'application sera accessible sur http://127.0.0.1:5000/

## Fonctionnalités

- Gestion des catégories de produits
- Ajout et visualisation des produits unitaires
- Création d'arcs composés à partir de produits existants
- Gestion des archers
- Assignation des arcs aux archers
- Export des listes en PDF

## Structure

- `app.py` : Application Flask principale
- `models.py` : Modèles de base de données
- `config.py` : Configuration
- `templates/` : Templates HTML
- `static/` : Fichiers statiques (CSS, JS)
- `migrations/` : Migrations de base de données