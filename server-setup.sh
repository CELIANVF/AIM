#!/bin/bash

# Server setup script - run this FIRST on your Linux server before deployment
# This sets up the server environment with required packages

set -e

echo "=========================================="
echo "Setting up Linux server for AIM deployment"
echo "=========================================="

# Update system
echo "[1/5] Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and dependencies
echo "[2/5] Installing Python and build tools..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    git \
    curl \
    wget

# Install Nginx
echo "[3/5] Installing Nginx web server..."
sudo apt-get install -y nginx

# Install supervisor (optional, for process management)
echo "[4/5] Installing Supervisor..."
sudo apt-get install -y supervisor

# Create application user (if not exists)
echo "[5/5] Setting up application user..."
if ! id "celian" &>/dev/null; then
    sudo useradd -m -s /bin/bash celian
    echo "User 'celian' created"
else
    echo "User 'celian' already exists"
fi

echo ""
echo "=========================================="
echo "Server setup complete!"
echo "=========================================="
echo ""
echo "IMPORTANT: ce script n'installe QUE les paquets système."
echo "Il ne démarre PAS l'application (Gunicorn) ni Nginx pour AIM."
echo ""
echo "Sur le serveur, après avoir cloné ou copié le dépôt AIM :"
echo "  cd ~/AIM   # ou le chemin où se trouve app.py"
echo "  chmod +x install-on-server.sh && ./install-on-server.sh votre-domaine.fr"
echo "  # accès par IP seulement : ./install-on-server.sh _"
echo ""
echo "Ou depuis votre PC (déploiement + service) :"
echo "  ./deploy.sh vrillaud-frizziero.fr"
echo "puis sur le serveur : ./install-on-server.sh (si Nginx pas encore configuré)"
echo ""
echo "HTTPS: sudo certbot --nginx -d vrillaud-frizziero.fr"
echo ""
