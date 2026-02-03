#!/bin/bash

# Deployment script for AIM Flask application to Linux server
# Usage: ./deploy.sh <server_ip_or_domain>

set -e

# Configuration
SERVER_USER="celian"
SERVER_HOST="${1:-vrillaud-frizziero.fr}"
APP_NAME="aim"
APP_DIR="/home/$SERVER_USER/$APP_NAME"
PYTHON_VERSION="3.10"

echo "=========================================="
echo "Deploying AIM application to $SERVER_HOST"
echo "=========================================="

# Step 1: Create app directory on server
echo "[1/6] Creating application directory on server..."
ssh $SERVER_USER@$SERVER_HOST << 'EOF'
    mkdir -p /home/celian/aim
    echo "App directory created/verified"
EOF

# Step 2: Upload project files
echo "[2/6] Uploading project files..."
scp -r ./* $SERVER_USER@$SERVER_HOST:$APP_DIR/
echo "Files uploaded successfully"

# Step 3: Setup Python environment on server
echo "[3/6] Setting up Python virtual environment..."
ssh $SERVER_USER@$SERVER_HOST << 'EOF'
    cd /home/celian/aim
    
    # Remove old venv if exists
    rm -rf venv
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    echo "Virtual environment created"
EOF

# Step 4: Install dependencies
echo "[4/6] Installing Python dependencies..."
ssh $SERVER_USER@$SERVER_HOST << 'EOF'
    cd /home/celian/aim
    source venv/bin/activate
    
    pip install -r requirements.txt
    pip install gunicorn  # Production WSGI server
    
    echo "Dependencies installed"
EOF

# Step 5: Initialize database
echo "[5/6] Initializing database..."
ssh $SERVER_USER@$SERVER_HOST << 'EOF'
    cd /home/celian/aim
    source venv/bin/activate
    
    # Run migrations if they exist
    if [ -d "migrations" ]; then
        flask db upgrade
    fi
    
    # Initialize database with seed data
    python3 << 'PYTHON'
from app import app, db, seed_categories

with app.app_context():
    db.create_all()
    seed_categories()
    print("Database initialized with seed data")
PYTHON
    
    echo "Database setup complete"
EOF

# Step 6: Create systemd service file for auto-start
echo "[6/6] Creating systemd service for auto-start..."
ssh $SERVER_USER@$SERVER_HOST << 'EOF'
    sudo tee /etc/systemd/system/aim.service > /dev/null << 'SERVICE'
[Unit]
Description=AIM Flask Application
After=network.target

[Service]
User=celian
WorkingDirectory=/home/celian/aim
ExecStart=/home/celian/aim/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 --timeout 60 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

    # Enable and start the service
    sudo systemctl daemon-reload
    sudo systemctl enable aim
    sudo systemctl start aim
    
    echo "Systemd service created and started"
EOF

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Configure Nginx as reverse proxy (see nginx.conf template)"
echo "2. Setup SSL certificate (Let's Encrypt recommended)"
echo "3. Access your app at: http://$SERVER_HOST"
echo ""
echo "Useful commands on server:"
echo "  - Check app status: sudo systemctl status aim"
echo "  - View logs: sudo journalctl -u aim -f"
echo "  - Restart app: sudo systemctl restart aim"
echo ""
