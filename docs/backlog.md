# Backlog initial – v0.1 Réalisons

## Épics
1. **Core procédural** : machine d’état (FSM), gestion des slots et check‑lists.
   - Voir la déclinaison complète en sous-issues détaillées dans [`docs/epic1_core_procedural_subissues.md`](docs/epic1_core_procedural_subissues.md).
   - Plan de tâches opérationnel pour les issues #46 → #60 : [`docs/tasks_core_procedural.md`](docs/tasks_core_procedural.md).
2. **Voix / Realtime** : intégration WebRTC, ASR, TTS et streaming.
3. **Sécurité & auth** : OIDC, RBAC, OPA, Vault.
4. **Données & persistance** : modèles DB, migrations, audit trail.
5. **Observabilité** : logs, traces, métriques, dashboard Grafana.
6. **Mobile** : écrans Procédure/Étape/Checklist, session chat, cache offline.
7. **Tests & Qualité** : unit, intégration, E2E Detox, CI/CD.

## Sprints (2 semaines chacun)
- **Sprint 0** : ADRs, définition des schémas, initialisation du repo mobile/backend/AI‑gateway.
- **Sprint 1** : API `runs`/`slots`/`commit-step`, Auth OIDC, stub OPA. Première procédure dummy.
- **Sprint 2** : Écrans mobiles de base, session chat, gestion des slots.
- **Sprint 3** : AI Gateway (Realtime), gestion vocale, tool‑calling restreint.
- **Sprint 4** : Audit trail, RLS, sauvegardes, observabilité.
- **Sprint 5** : Tests E2E, durcissement sécurité, packaging.
- **Sprint 6** : Stabilisation et démo v0.1.
