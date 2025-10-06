# Architecture v0.1 – Réalisons

## Vue d’ensemble
L’architecture suit un modèle **client‑serveur** avec trois services principaux :

1. **Application mobile (React Native)** : interface utilisateur pour la conversation (voix et texte). Elle communique avec l’API via HTTPS.
2. **Service applicatif (FastAPI)** : gère l’authentification, les procédures et la persistance des données (PostgreSQL). Il expose des endpoints REST et sécurisés (OIDC).
3. **Passerelle IA** : service dédié qui orchestre les appels vers les modules de reconnaissance vocale, de synthèse vocale et vers le modèle IA (GPT‑4o ou équivalent). Il implémente des fonctions outillées afin que le LLM ne puisse pas accéder directement aux bases de données.

Toutes les données sont stockées en **Suisse** avec chiffrement au repos et en transit. Des politiques **OPA** assurent un contrôle d’accès fin aux ressources et slots. Un **audit trail** en append‑only enregistre toutes les opérations.

## Diagramme de conteneurs (C4)

```
[Mobile RN]──https/mTLS──>[BFF/API]──SQL──>[PostgreSQL]
      │                          │ │                   └─[pgvector]
      │                          │ └─cache───────────>[Redis]
      │                          └─auth OIDC────────>[Keycloak]
      │                          └─policy query─────>[OPA]
      │                          └─secrets──────────>[Vault]
      └─WebRTC/Realtime──>[AI-Gateway]──tool‑calls──>[BFF]
                                 └─ASR/TTS/LLM (managé ou edge)
```

## Sécurité
- Authentification **OIDC** via Keycloak.
- Chiffrement au repos (PGCrypto) et en transit (TLS/mTLS).
- Politique d’accès via **OPA**.
- Audit trail (table `events`) respectant les principes **ALCOA+**.

## Prochaines étapes
Voir `../README.md` pour les instructions d’installation. Les diagrammes détaillés (niveau composant) et les ADR (Architecture Decision Records) se trouvent dans `docs/backlog.md`.
