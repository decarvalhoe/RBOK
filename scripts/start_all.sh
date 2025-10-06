#!/bin/bash
# Script pour démarrer les services en local
cd "$(dirname "$0")/.."
# Démarrer le backend en arrière-plan
python3 backend/app/main.py &
# Démarrer AI Gateway en arrière-plan
python3 ai_gateway/main.py &
# Démarrer le serveur mobile (Metro bundler)
cd mobile && npm start
