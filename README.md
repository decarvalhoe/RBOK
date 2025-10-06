# Projet « Réalisons » v0.1

## Aperçu
Ce dépôt contient l’ossature de départ pour développer la **version 0.1** de l’assistant procédural « Réalisons ». L’objectif est de livrer une première démonstration au **31 janvier 2026**. Vous trouverez une structure de monorepo avec trois briques principales : **mobile**, **backend** et **AI Gateway**, ainsi que des documents techniques.

## Arborescence
- `mobile/` – Projet **React Native** (TypeScript) pour iOS/Android.
- `backend/` – API **FastAPI** gérant l’authentification, les procédures et la persistance des données.
- `ai_gateway/` – Service orchestrant la reconnaissance vocale, la synthèse vocale et l’appel au modèle IA (GPT‑4o ou équivalent) via des fonctions restreintes.
- `docs/` – Documentation d’architecture, schémas JSON, backlog initial.
- `scripts/` – Scripts utilitaires (ex. démarrage local).
- `README.md` – Présent document.

## Pré-requis
- **Node.js ≥ 18** et **npm/yarn** pour l’application mobile.
- **Python ≥ 3.9** et **pip** pour les services serveur.
- **Poetry ou virtualenv** pour isoler les dépendances Python (optionnel).

## Installation rapide
1. **Cloner** ce dépôt :
   ```sh
git clone <url-du-repo> && cd realisons_starter_pack
   ```
2. **Mobile** :
   ```sh
cd mobile
npm install # installe les dépendances React Native
npx pod-install # pour iOS (via cocoa‑pods)
npm run android # ou `npm run ios` selon la plateforme
   ```
3. **Backend** :
   ```sh
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
   ```
4. **AI Gateway** :
   ```sh
cd ai_gateway
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
   ```

## Prochaines étapes
- Compléter les endpoints FastAPI dans `backend/app/api` et les modèles dans `backend/app/models`.
- Définir vos **procédures** (FSM) dans `docs/json_schema_procedure_v1.json` et intégrer un parseur dans `backend`.
- Implémenter la logique du **AI Gateway** : gestion des appels ASR/TTS, redaction des réponses, appels au LLM.
- Ajouter des tests unitaires et end‑to‑end (E2E) selon la stratégie décrite dans `docs/backlog.md`.

Pour plus d’informations sur l’architecture, consultez `docs/architecture.md`.
