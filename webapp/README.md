# Réalisons Webapp

## Configuration par variables d'environnement

| Nom | Description | Valeur par défaut | Recommandations de sécurité |
| --- | ----------- | ----------------- | ---------------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | URL de base de l'API FastAPI utilisée pour les appels REST. | `http://localhost:8000` | Aucune donnée sensible ne doit être exposée ; utilisez un domaine HTTPS en production. |
| `NEXT_PUBLIC_AI_GATEWAY_BASE_URL` | URL du service AI Gateway pour les fonctionnalités voix/LLM. | `http://localhost:8010` | Conserver la valeur publique mais privilégier le HTTPS et limiter l'accès réseau. |

1. Copiez `.env.example` vers `.env.local` (ou `.env`) :
   ```bash
   cp .env.example .env.local
   ```
2. Ajustez les URLs pour votre environnement (les clés privées ne doivent jamais être ajoutées car seules les variables `NEXT_PUBLIC_` sont exposées côté client).
3. Les valeurs doivent être revues et mises à jour lors de chaque rotation d'URL backend/gateway.

Le fichier `next.config.js` charge automatiquement ces variables pour les commandes `next dev`, `next build` et `next start`. Les tests Jest chargent également `.env` via `dotenv`.

## Prérequis
- Node.js 18+
- npm 9+

## Installation
```bash
cd webapp
npm install
```

## Développement
```bash
npm run dev
```
L'application est servie sur `http://localhost:3000`.

## Build de production
```bash
npm run build
npm run start
```

## Tests
```bash
npm test
```
