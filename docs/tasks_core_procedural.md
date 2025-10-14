# Plan de tâches pour les issues core procédurales (#46 → #60)

Ce document décompose chaque issue ouverte du bloc "Core procédural" en tâches concrètes
à réaliser. Les issues sont listées du plus fondamental (modèles & migrations) au plus
aval (documentation & validation fonctionnelle) pour faciliter la planification.

## #46 – Consolider les modèles de données procéduraux
- [ ] Cartographier les colonnes JSON existantes et les champs qu'elles contiennent.
- [ ] Concevoir les modèles relationnels (slots, checklists, historiques) et leur diagramme.
- [ ] Mettre à jour les modèles SQLAlchemy et les tests unitaires associés.
- [ ] Documenter les nouveaux modèles dans `docs/procedures.md`.

## #47 – Créer les migrations Alembic pour le schéma procédural
- [ ] Générer la révision couvrant les nouvelles tables/contraintes depuis les modèles.
- [ ] Vérifier l'upgrade/downgrade sur une base vierge (SQLite & Postgres local).
- [ ] Ajouter la procédure de lancement de migration dans la documentation technique.

## #48 – Générer une révision Alembic couvrant toutes les nouvelles tables et contraintes
- [ ] Lister les dépendances entre tables pour garantir l'ordre de création.
- [ ] Implémenter la révision finale et la valider via `alembic upgrade head`.
- [ ] Ajouter un test automatisé de migration dans la CI.

## #49 – Refondre les colonnes JSON au profit de modèles relationnels dédiés
- [ ] Supprimer les champs JSON obsolètes et migrer les données existantes.
- [ ] Introduire les relations ORM (slots, checklist_items, run_steps).
- [ ] Couvrir la rétrocompatibilité via un script de migration de données.

## #50 – Implémenter la machine à états finis (FSM) des procédures
- [ ] Définir les états et transitions autorisées (pending → in_progress → completed/failed).
- [ ] Coder le service FSM avec journalisation et hooks d'audit.
- [ ] Intégrer le FSM dans les endpoints `runs` et scénarios de tests.

## #51 – Centraliser les transitions pending → in_progress → completed/failed
- [ ] Déporter la logique de transition des endpoints vers un service unique.
- [ ] Appliquer les vérifications métier (préconditions, validations) avant transition.
- [ ] Produire une documentation de séquence d'état pour l'onboarding des devs.

## #52 – Exposer /procedures (GET liste, GET détail, POST création)
- [ ] Créer le router FastAPI `/procedures` avec schémas Pydantic dédiés.
- [ ] Brancher la couche d'accès aux données (lecture + création).
- [ ] Couvrir le endpoint par des tests d'intégration et la documentation OpenAPI.

## #53 – Gérer /runs, la progression des étapes et les commits
- [ ] Créer le router FastAPI `/runs` pour les opérations CRUD et progression.
- [ ] Connecter les services FSM, validation de slots et gestion de checklists.
- [ ] Tester la progression complète d'un run, y compris les scénarios d'erreur.

## #54 – Valider les données collectées selon leur type et leurs contraintes
- [ ] Formaliser les types de slots (texte, booléen, media, etc.) et leurs règles.
- [ ] Implémenter le module de validation typée avec messages localisables.
- [ ] Ajouter des tests unitaires couvrant chaque type et cas limite.

## #55 – Suivre la complétion des checklists au niveau des runs
- [ ] Modéliser les éléments de checklist et leur statut par run/étape.
- [ ] Implémenter les services d'agrégation et de mise à jour des statuts.
- [ ] Exposer la complétion via les endpoints et tracer dans l'audit trail.

## #56 – Mettre en cache listes et détails afin de réduire la latence
- [ ] Configurer Redis (ou stub) et définir la stratégie TTL/invalidation.
- [ ] Ajouter une couche cache sur les endpoints `/procedures` et `/runs`.
- [ ] Instrumenter la métrique de taux de hit/miss et documenter le fallback.

## #57 – Atteindre ≥ 80 % de couverture sur la logique procédurale
- [ ] Identifier les modules critiques (FSM, validation, cache) et leurs gaps de tests.
- [ ] Écrire des tests unitaires ciblés pour atteindre le seuil de 80 %.
- [ ] Automatiser le rapport de couverture dans la CI (badge + seuil bloquant).

## #58 – Garantir le parcours complet via l'API
- [ ] Écrire des tests d'intégration E2E couvrant création de procédure et exécution.
- [ ] Mock/Tupler les services externes pour obtenir un scénario stable.
- [ ] Ajouter les tests au pipeline CI avec un environnement éphémère.

## #59 – Proposer un scénario bout en bout pour la validation fonctionnelle
- [ ] Construire un jeu de données de démonstration (procédure complète avec runs).
- [ ] Décrire le walkthrough fonctionnel dans `docs/procedures.md`.
- [ ] Préparer un script/guide facilitant la validation par les parties prenantes.

## #60 – Mettre à jour la documentation technique et l'OpenAPI
- [ ] Réconcilier les schémas JSON, la documentation écrite et l'OpenAPI générée.
- [ ] Ajouter les nouvelles routes/propriétés dans `docs/openapi.json`.
- [ ] Publier un changelog indiquant les impacts pour les intégrateurs.

