# Réalisons Webapp

## Variables d'environnement

| Nom | Description | Valeur par défaut |
| --- | ----------- | ----------------- |
| `NEXT_PUBLIC_API_BASE_URL` | URL de base de l'API FastAPI consommée par l'application web. | `http://localhost:8000` |

Définissez cette variable avant d'exécuter `npm run dev` si votre API est exposée sur une autre adresse.

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
