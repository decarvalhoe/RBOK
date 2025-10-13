# Projet RBOK - Assistant Procédural v0.1

## Aperçu

**RBOK** est un assistant procédural intelligent conçu pour guider les utilisateurs à travers des processus complexes via une interface conversationnelle naturelle (voix et texte). Le projet vise à créer un outil d'IA neuro-symbolique capable de maintenir le contexte procédural tout en collectant et validant des données de manière structurée.

### Objectifs v0.1

La version 0.1 se concentre sur la création d'une architecture robuste, sécurisée et souveraine, avec une première application web et une portabilité future vers des applications mobiles natives React Native. **Date de livraison cible : 31 janvier 2026**.

## Architecture

L'architecture est basée sur un modèle de microservices avec trois composants principaux :

### Composants

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Web App** | Next.js + React + TypeScript | Interface utilisateur conversationnelle |
| **Backend API** | FastAPI + Python | Gestion des procédures, utilisateurs et données |
| **AI Gateway** | FastAPI + Python | Orchestration des appels IA (ASR/TTS/LLM) |

### Infrastructure

- **Base de données** : PostgreSQL (hébergé en Suisse) avec pgvector pour les fonctionnalités RAG
- **Cache** : Redis pour les sessions et données temporaires
- **Authentification** : Keycloak (OIDC/OAuth2) avec MFA
- **Politiques** : Open Policy Agent (OPA) pour le contrôle d'accès granulaire
- **Secrets** : HashiCorp Vault pour la gestion sécurisée
- **Observabilité** : OpenTelemetry + Loki/Grafana + Sentry (voir [docs/observability.md](docs/observability.md) pour la configuration et l'exploitation)

## Fonctionnalités Clés

### Moteur Procédural
- **Machine à états finis (FSM)** pour le suivi des procédures
- **Collecte de slots** structurée avec validation
- **Checklists dynamiques** par étape
- **Audit trail complet** (ALCOA+) pour la traçabilité

### Interface Conversationnelle
- **Interaction vocale** via WebRTC et ASR/TTS
- **Chat textuel** en temps réel
- **Contexte persistant** entre les sessions
- **Guidage intelligent** basé sur l'état de la procédure

### Sécurité et Conformité
- **Souveraineté des données** (hébergement Suisse)
- **Chiffrement** au repos et en transit
- **Contrôle d'accès** granulaire (RBAC/ABAC)
- **Journalisation immuable** (WORM)

## Structure du Projet

```
├── webapp/                 # Application web Next.js
│   ├── app/               # Pages et composants
│   └── package.json       # Dépendances frontend
├── backend/               # API FastAPI
│   ├── app/              # Code source backend
│   └── requirements.txt   # Dépendances Python
├── ai_gateway/           # Service IA dédié
│   ├── main.py          # Point d'entrée
│   └── requirements.txt  # Dépendances IA
├── mobile/               # Application React Native (future)
├── docs/                 # Documentation
│   ├── architecture.md   # Architecture détaillée
│   ├── backlog.md       # Backlog et sprints
│   ├── observability.md  # Stack d'observabilité et runbooks
│   └── *.json           # Schémas et exemples
└── scripts/             # Scripts utilitaires
```

## Démarrage Rapide

### Prérequis
- **Node.js** ≥ 18 (pour l'application web)
- **Python** ≥ 3.9 (pour les services backend)
- **Docker** (optionnel, pour les services d'infrastructure)

### Configuration des variables d'environnement

Chaque service possède un fichier `.env.example` (`backend/`, `ai_gateway/`, `webapp/`). Copiez-le vers `.env` (ou `.env.local` pour Next.js) et remplacez les valeurs sensibles :

```bash
cp backend/.env.example backend/.env
cp ai_gateway/.env.example ai_gateway/.env
cp webapp/.env.example webapp/.env.local
```

- Les secrets (`REALISONS_SECRET_KEY`, `AI_GATEWAY_OPENAI_API_KEY`, mots de passe DB, etc.) doivent être générés via un coffre à secrets et tournés régulièrement.
- Ne commitez jamais les fichiers `.env`. Les services refuseront de démarrer si les valeurs critiques sont manquantes ou utilisent les valeurs de démonstration.
### Utilisation avec Docker (développement)

Un environnement Docker Compose est fourni pour exécuter l'API, la passerelle IA, le frontend, PostgreSQL et Redis avec hot-reload.

1. **Configurer les variables sensibles (facultatif)**
   - Les valeurs par défaut conviennent pour un test local rapide.
   - Pour utiliser de vraies clés, exportez-les avant le lancement :
     ```bash
     export AI_GATEWAY_OPENAI_API_KEY="sk-..."
     export NEXT_PUBLIC_API_URL="http://localhost:8000"
     ```
2. **Construire et lancer l'ensemble des services**
   ```bash
   docker compose up --build
   ```
   Les services sont disponibles sur :
   - http://localhost:3000 pour la webapp (Next.js avec hot-reload)
   - http://localhost:8000 pour l'API FastAPI
   - http://localhost:8100 pour la passerelle IA
3. **Inspecter les journaux**
   ```bash
   docker compose logs -f backend
   ```
4. **Arrêter et nettoyer**
   ```bash
   docker compose down
   ```

#### Variables d'environnement principales

| Service      | Variable                              | Valeur par défaut                                   |
|--------------|----------------------------------------|-----------------------------------------------------|
| Backend      | `DATABASE_URL`                         | `postgresql+asyncpg://rbok:rbok@postgres:5432/rbok` |
| Backend      | `REDIS_URL`                            | `redis://redis:6379/0`                              |
| Backend      | `OTEL_EXPORTER_OTLP_ENDPOINT`          | *(vide)* – URL du collecteur OTLP (ex. `https://otel.example.com:4318`) |
| Backend      | `OTEL_SERVICE_NAME`                    | `rbok-backend`                                      |
| AI Gateway   | `AI_GATEWAY_OPENAI_API_KEY`            | `changeme` (à remplacer pour un usage réel)        |
| AI Gateway   | `AI_GATEWAY_ALLOWED_ORIGINS`           | `http://localhost:3000`                             |
| AI Gateway   | `OTEL_EXPORTER_OTLP_ENDPOINT`          | *(vide)* – URL du collecteur OTLP pour les logs     |
| AI Gateway   | `OTEL_SERVICE_NAME`                    | `rbok-ai-gateway`                                   |
| Webapp       | `NEXT_PUBLIC_API_URL`                  | `http://localhost:8000`                             |
| Webapp       | `NEXT_PUBLIC_AI_GATEWAY_URL`           | `http://localhost:8100`                             |

Les valeurs peuvent être surchargées via des variables d'environnement exportées ou un fichier `.env` chargé par Docker Compose.

### Utilisation avec Docker (production)

Pour simuler un déploiement de production (sans hot-reload ni montage de volumes), utilisez le fichier d'override :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Assurez-vous de fournir une clé OpenAI valide :

```bash
export AI_GATEWAY_OPENAI_API_KEY="sk-..."
```

### Stack locale (installation manuelle)

### Installation

1. **Cloner le repository**
   ```bash
   git clone https://github.com/decarvalhoe/RBOK.git
   cd RBOK
   ```

2. **Backend API**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   alembic upgrade head
   # Démarrer Redis en local (Docker)
   docker run --rm -p 6379:6379 redis:7-alpine
   # ou exporter REDIS_URL si un service managé est utilisé
   export REDIS_URL=redis://localhost:6379/0
   uvicorn app.main:app --reload --port 8000
   ```

### Tests et couverture

Les suites de tests automatisés sont configurées pour produire des rapports de couverture et échouer si les seuils minimaux ne
sont pas atteints. Voici les commandes principales :

- **Backend API** :
  ```bash
  cd backend
  pytest
  ```
- **Passerelle IA** :
  ```bash
  cd ai_gateway
  pytest
  ```
- **Webapp Next.js** :
  ```bash
  cd webapp
  npm run test:ci
  ```
- **Application mobile React Native** :
  ```bash
  cd mobile
  npm test -- --ci
  ```

Le workflow GitHub Actions [`CI`](.github/workflows/ci.yml) exécute automatiquement ces commandes sur chaque branche et pull req
uest. Les fusions sont bloquées tant que l'une de ces étapes échoue.

  #### Authentification Keycloak & OPA

  L'API s'appuie désormais sur un serveur **Keycloak** pour valider les tokens OIDC et sur **OPA** pour les politiques fines. Configurez les variables d'environnement suivantes avant de démarrer le service :

  | Variable | Description | Valeur d'exemple |
  |----------|-------------|------------------|
  | `KEYCLOAK_SERVER_URL` | URL racine du serveur Keycloak | `http://localhost:8081` |
  | `KEYCLOAK_REALM` | Nom du realm contenant le client RBOK | `realison` |
  | `KEYCLOAK_CLIENT_ID` | ID du client public/confidentiel | `realison-backend` |
  | `KEYCLOAK_CLIENT_SECRET` | Secret du client (si confidentiel) | `super-secret` |
  | `KEYCLOAK_AUDIENCE` | Audience attendue pour les tokens (optionnel) | `realison-backend` |
  | `KEYCLOAK_ROLE_MAPPING` | Mapping JSON `{"kc-role": "app-role"}` | `{"app-admin": "admin"}` |
  | `OPA_URL` | Endpoint HTTP OPA évaluant la décision (`/v1/data/...`) | `http://localhost:8181/v1/data/realison/authz` |
  | `OPA_TIMEOUT_SECONDS` | Délai max (s) pour une décision OPA | `2.0` |

  Le backend n'émet plus de tokens localement : il délègue l'authentification à Keycloak.

  ```bash
  # Récupération d'un token utilisateur via Keycloak (password grant)
  export KEYCLOAK_SERVER_URL=http://localhost:8081
  export KEYCLOAK_REALM=realison
  export KEYCLOAK_CLIENT_ID=realison-backend
  export KEYCLOAK_CLIENT_SECRET=super-secret

  curl -X POST "$KEYCLOAK_SERVER_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=$KEYCLOAK_CLIENT_ID" \
    -d "client_secret=$KEYCLOAK_CLIENT_SECRET" \
    -d "grant_type=password" \
    -d "username=alice" \
    -d "password=adminpass"
  ```

  Les endpoints `POST /auth/token`, `POST /auth/refresh` et `POST /auth/introspect` agissent comme proxys vers Keycloak pour respectivement générer, rafraîchir et introspecter les tokens. Avant toute action sensible (`POST /procedures`, `POST /runs`), l'API vérifie à la fois le rôle RBAC et une décision OPA (`allow=true`).

  #### Tests d'intégration Keycloak/OPA

  Un scénario d'intégration est disponible dans `backend/tests/integration`. Il démarre Keycloak et OPA via `docker compose` et vérifie les décisions d'autorisation de bout en bout :

  ```bash
  docker compose -f backend/tests/integration/docker-compose.yml up -d
  pytest backend/tests/integration/test_authz_integration.py
  docker compose -f backend/tests/integration/docker-compose.yml down -v
  ```

  Les tests unitaires classiques peuvent être exécutés via `pytest backend/tests` (ils utilisent des dépendances FastAPI surchargées pour éviter l'appel aux services externes).
   #### Cache Redis

   L'API s'appuie sur Redis pour mettre en cache les listes de procédures, les détails et les exécutions. En développement, un conteneur Docker suffit ; en production, configurez les variables suivantes selon votre plateforme d'hébergement :

   | Variable | Description | Valeur par défaut |
   |----------|-------------|-------------------|
   | `REDIS_URL` | Chaîne de connexion complète si disponible. | Générée à partir des variables ci-dessous. |
   | `REDIS_HOST` | Hôte du serveur Redis. | `localhost` |
   | `REDIS_PORT` | Port du serveur Redis. | `6379` |
   | `REDIS_DB` | Index de base de données Redis. | `0` |
   | `REDIS_PASSWORD` | Mot de passe si nécessaire. | *(vide)* |
   | `REDIS_TLS` | `true`/`false` pour activer TLS (`rediss://`). | `false` |

   L'invalidation du cache est automatique lors des créations/updates/suppressions de procédures. Assurez-vous simplement que l'instance Redis est accessible depuis l'API dans vos environnements de déploiement (VPC, service managé, etc.).

   #### Authentification JWT de développement

   L'API expose un flux OAuth2 password simplifié pour générer des tokens Bearer (JWT) destinés aux tests :

   ```bash
   # Récupération d'un token administrateur
   curl -X POST http://localhost:8000/auth/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=alice&password=adminpass"
   ```

   Deux comptes in-memory sont disponibles par défaut :

   | Utilisateur | Rôle  | Mot de passe |
   |-------------|-------|--------------|
   | `alice`     | admin | `adminpass`  |
   | `bob`       | user  | `userpass`   |

   Les appels nécessitant des droits d'écriture (ex. `POST /procedures`) doivent inclure l'en-tête :

   ```http
   Authorization: Bearer <token>
   ```

   Les utilisateurs standards peuvent lancer des exécutions (`POST /runs`) tandis que seuls les administrateurs peuvent créer des procédures.

   #### Configuration

   Les variables d'environnement suivantes permettent d'ajuster le comportement de l'API :

   | Variable | Description | Valeur par défaut |
   |----------|-------------|-------------------|
   | `BACKEND_ALLOW_ORIGINS` | Liste séparée par des virgules des origines autorisées pour CORS. | `http://localhost:3000` |
   | `BACKEND_RATE_LIMIT` | Limite de requêtes appliquée par défaut (syntaxe `nombre/période`). | `120/minute` |
   | `BACKEND_RATE_LIMIT_ENABLED` | Active (`true`) ou désactive (`false`) le throttling. | `true` |
   | `BACKEND_RATE_LIMIT_HEADERS_ENABLED` | Active l'exposition des en-têtes `X-RateLimit-*` et `Retry-After`. | `true` |

   En production, `BACKEND_ALLOW_ORIGINS` accepte des domaines multiples (par ex. `https://app.example.com,https://admin.example.com`).
   Les réponses HTTP `429 Too Many Requests` retournées par l'API incluent désormais ces en-têtes et sont documentées dans l'OpenAPI.

3. **Application Web**
   ```bash
   cd webapp
   npm install
   npm run dev
   ```

4. **AI Gateway**
   ```bash
   cd ai_gateway
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python main.py
   ```
   Consultez également `docs/ai_gateway.md` pour la description détaillée des endpoints et de la configuration.

### Docker Compose de développement

Un fichier `docker-compose.yml` est fourni pour lancer les trois services avec leurs fichiers `.env` respectifs :

```bash
docker compose up --build
```

Chaque service charge automatiquement son fichier `.env` via `env_file`. Copiez d'abord les `.env.example` et ne versionnez jamais les fichiers réels.

### Accès
- **Application web** : http://localhost:3000
- **API Backend** : http://localhost:8000
- **Documentation API** : http://localhost:8000/docs

### Dépannage (Docker)

- **Erreur `OPENAI API key must be provided...`** : définissez `AI_GATEWAY_OPENAI_API_KEY` avant de lancer `docker compose up`.
- **Hot-reload qui ne déclenche pas** : vérifiez que vos fichiers sont bien montés (`./backend`, `./ai_gateway`, `./webapp`). Un `docker compose restart <service>` force la prise en compte des volumes.
- **Port déjà utilisé** : modifiez `BACKEND_PORT`, `AI_GATEWAY_PORT` ou `WEBAPP_PORT` dans votre environnement avant le lancement.
## Qualité du code et linting

### Frontend (webapp)
1. Installer les dépendances :
   ```bash
   cd webapp
   npm install
   ```
2. Lancer l'analyse ESLint :
   ```bash
   npm run lint
   ```
3. Vérifier la mise en forme Prettier :
   ```bash
   npm run format
   ```
4. Pour corriger automatiquement les problèmes détectés :
   ```bash
   npm run lint:fix
   npm run format:fix
   ```

### Backend (FastAPI)
1. Créer un environnement virtuel et installer les dépendances :
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # Windows : .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Lancer Ruff pour l'analyse statique :
   ```bash
   make lint
   ```
3. Vérifier la mise en forme Black :
   ```bash
   make format-check
   ```
4. Pour appliquer automatiquement les correctifs :
   ```bash
   make lint-fix
   make format
   ```
5. Les mêmes vérifications sont disponibles via tox :
   ```bash
   tox -e lint
   tox -e format
   ```

## Roadmap v0.1

### Sprints Planifiés (2 semaines chacun)

| Sprint | Période | Objectifs Principaux |
|--------|---------|---------------------|
| **S0** | Préparation | ADR, C4, schémas, scaffolds |
| **S1** | Backend Core | DB, BFF, OIDC, OPA |
| **S2** | Frontend Core | Interface web, chat, slots |
| **S3** | AI Integration | Gateway IA, voix, tool-calling |
| **S4** | Data & Security | Audit trail, RLS, observabilité |
| **S5** | Quality & Testing | Tests E2E, SAST/DAST, performance |
| **S6** | Stabilisation | Documentation, packaging, déploiement |

## Épics GitHub

Les épics suivants ont été créés comme issues GitHub :

1. **Epic 1** : Core procédural (FSM/slots/checklists) - [Issue #1](https://github.com/decarvalhoe/RBOK/issues/1)
2. **Epic 2** : Interface utilisateur web - [Issue #2](https://github.com/decarvalhoe/RBOK/issues/2)
3. **Epic 3** : Voix / Realtime (WebRTC + ASR/TTS) - [Issue #3](https://github.com/decarvalhoe/RBOK/issues/3)
4. **Epic 4** : Sécurité (OIDC, OPA, Vault) - [Issue #4](https://github.com/decarvalhoe/RBOK/issues/4)
5. **Epic 5** : Données (Postgres, RLS, audit) - [Issue #5](https://github.com/decarvalhoe/RBOK/issues/5)
6. **Epic 6** : Observabilité (Otel, Sentry, Loki/Grafana) - [Issue #6](https://github.com/decarvalhoe/RBOK/issues/6)
7. **Epic 7** : Qualité (tests, E2E, perf) - [Issue #7](https://github.com/decarvalhoe/RBOK/issues/7)

## Estimation des Coûts

### Développement (3-4 mois)
- **Local Suisse** : 55-95k CHF
- **Mix Suisse + Nearshore** : 38-72k CHF
- **Effort total** : 71-89 jours-homme

### Infrastructure Mensuelle (Suisse)
- **Option Économique** : 650-1400 CHF/mois
- **Option Standard** : 850-2100 CHF/mois
- **Option Premium** : 900-2100 CHF/mois

## Intégration continue

Le workflow GitHub Actions `ci.yml` prépare automatiquement les fichiers `.env` à partir des gabarits et injecte les secrets requis (ex : `REALISONS_SECRET_KEY`, `AI_GATEWAY_OPENAI_API_KEY`). Configurez ces secrets dans les paramètres du dépôt avant d'activer la CI.

## Contribution

Ce projet suit une méthodologie **Scrum** avec des principes **6 Sigma** pour la qualité. Consultez le [backlog](docs/backlog.md) pour les détails des sprints et user stories.

## Licence

[À définir]

---

**RBOK v0.1** - Assistant Procédural Intelligent  
*Développé avec Manus.AI et OpenAI*
