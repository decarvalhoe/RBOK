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

## Signalisation WebRTC

Le backend FastAPI expose désormais un **service de signalisation** persistant permettant la
négociation de sessions WebRTC entre pairs :

1. Le client (web ou mobile) récupère la configuration des serveurs ICE via `GET /webrtc/config`.
2. L’initiateur crée une session avec son offre SDP (`POST /webrtc/sessions`). L’API stocke
   l’offre, les métadonnées et initialise la liste de candidats ICE.
3. Le répondant consulte la session puis publie sa réponse (`POST /webrtc/sessions/{id}/answer`).
4. Les candidats ICE sont échangés via `POST /webrtc/sessions/{id}/candidates` et consolidés côté
   serveur afin que chaque pair puisse les récupérer.
5. La session peut être clôturée explicitement (`POST /webrtc/sessions/{id}/close`) pour
   conserver l’historique tout en signalant la fin de la négociation.

### Considérations opérationnelles

- Les URL des serveurs **STUN/TURN** sont injectées via les variables d’environnement
  `WEBRTC_STUN_SERVERS` et `WEBRTC_TURN_SERVERS`. Les secrets associés au TURN sont gérés via
  `WEBRTC_TURN_USERNAME` / `WEBRTC_TURN_PASSWORD`.
- L’API `/webrtc/config` ne retourne que les champs nécessaires aux clients afin d’éviter toute
  exposition involontaire de configuration interne.
- Les tables `webrtc_sessions` conservent l’historique des échanges pour audit et troubleshooting.
- En production, il est recommandé de coupler ces endpoints à des mécanismes d’expiration ou de
  nettoyage (cron) pour purger les sessions inactives.

## Prochaines étapes
Voir `../README.md` pour les instructions d’installation. Les diagrammes détaillés (niveau composant) et les ADR (Architecture Decision Records) se trouvent dans `docs/backlog.md`.
