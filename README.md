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
- **Observabilité** : OpenTelemetry + Loki/Grafana + Sentry

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
│   └── *.json           # Schémas et exemples
└── scripts/             # Scripts utilitaires
```

## Démarrage Rapide

### Prérequis
- **Node.js** ≥ 18 (pour l'application web)
- **Python** ≥ 3.9 (pour les services backend)
- **Docker** (optionnel, pour les services d'infrastructure)

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
   uvicorn app.main:app --reload --port 8000
   ```

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

### Accès
- **Application web** : http://localhost:3000
- **API Backend** : http://localhost:8000
- **Documentation API** : http://localhost:8000/docs

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

## Contribution

Ce projet suit une méthodologie **Scrum** avec des principes **6 Sigma** pour la qualité. Consultez le [backlog](docs/backlog.md) pour les détails des sprints et user stories.

## Licence

[À définir]

---

**RBOK v0.1** - Assistant Procédural Intelligent  
*Développé avec Manus.AI et OpenAI*
