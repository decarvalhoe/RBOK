# Réalisons Webapp

## Configuration par variables d'environnement

| Nom                               | Description                                                  | Valeur par défaut       | Recommandations de sécurité                                                            |
| --------------------------------- | ------------------------------------------------------------ | ----------------------- | -------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL`        | URL de base de l'API FastAPI utilisée pour les appels REST.  | `http://localhost:8000` | Aucune donnée sensible ne doit être exposée ; utilisez un domaine HTTPS en production. |
| `NEXT_PUBLIC_AI_GATEWAY_BASE_URL` | URL du service AI Gateway pour les fonctionnalités voix/LLM. | `http://localhost:8010` | Conserver la valeur publique mais privilégier le HTTPS et limiter l'accès réseau.      |

1. Copiez `.env.example` vers `.env.local` (ou `.env`) :
   ```bash
   cp .env.example .env.local
   ```
2. Ajustez les URLs pour votre environnement (les clés privées ne doivent jamais être ajoutées car seules les variables `NEXT_PUBLIC_` sont exposées côté client).
3. Les valeurs doivent être revues et mises à jour lors de chaque rotation d'URL backend/gateway.

Le fichier `next.config.js` charge automatiquement ces variables pour les commandes `next dev`, `next build` et `next start`. Les tests Jest chargent également `.env` via `dotenv`.
| Nom | Description | Valeur par défaut |
| -------------------------- | ------------------------------------------------------------- | ----------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | URL de base de l'API FastAPI consommée par l'application web. | `http://localhost:8000` |

Définissez cette variable avant d'exécuter `npm run dev` si votre API est exposée sur une autre adresse.

# Réalisons Webapp

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

L'application est servie sur `http://localhost:3000` avec Tailwind CSS.

## Build de production

```bash
npm run build
npm run start
```

## Tests

```bash
npm test
```

## Tests de style

```bash
npm test
```

Exécute les tests Jest/Testing Library qui vérifient la présence des classes Tailwind essentielles.

## Tests

```bash
npm test
```

Exécute les tests Jest/Testing Library qui couvrent les interactions de formulaire et la mise en page de la page d'accueil.

## Validation du formulaire de message

- Les règles de validation sont partagées entre le frontend et le backend via le fichier [`shared/message-constraints.json`](../shared/message-constraints.json). Toute évolution doit être réalisée dans ce fichier pour conserver la cohérence des limites.
- Un message est obligatoire et doit contenir au moins 1 caractère utile après suppression des espaces superflus.
- Un message ne peut pas dépasser 1 000 caractères. La zone de saisie affiche le nombre de caractères restants et les erreurs sont annoncées aux technologies d'assistance grâce aux attributs `aria-invalid` et `aria-live`.
- Les messages d'état (envoi en cours, erreurs côté assistant) sont également diffusés avec `aria-live="polite"` afin de rester accessibles.

Ces contraintes sont partagées avec le backend via ce fichier commun, ce qui évite l'envoi de requêtes invalides vers l'API.
