# Webapp Réalisons

## Variables d'environnement

| Nom                        | Description                                                   | Valeur par défaut       |
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

L'application est servie sur `http://localhost:3000` avec Tailwind CSS.

## Build de production

```bash
npm run build
npm run start
```

## Tests de style

```bash
npm test
```

Exécute les tests Jest/Testing Library qui vérifient la présence des classes Tailwind essentielles.
