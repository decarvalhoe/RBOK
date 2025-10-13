# Epic 1 – Sous-issues "Core procédural"

## 1. Consolider les modèles de données procéduraux
- **Objectif** : remplacer les colonnes JSON génériques par des modèles relationnels pour slots et checklists et enrichir `ProcedureRun`.
- **Livrables** : modèles SQLAlchemy (`ProcedureSlot`, `ProcedureChecklistItem`, etc.), contraintes d'intégrité, documentation des champs.
- **Références** : `backend/app/models.py`, `backend/app/database.py`.

## 2. Créer les migrations Alembic pour le schéma procédural
- **Objectif** : générer une révision couvrant les nouvelles tables et contraintes.
- **Livrables** : script Alembic complet (upgrade/downgrade) validé sur base vierge.
- **Références** : `backend/alembic/versions/`, `backend/app/models.py`.

## 3. Implémenter la machine à états finis (FSM) des procédures
- **Objectif** : centraliser les transitions `pending → in_progress → completed/failed`.
- **Livrables** : module de service `services/procedures/fsm.py`, intégration audit trail.
- **Références** : `backend/app/services/audit.py`.

## 4. Développer les endpoints REST de gestion des procédures
- **Objectif** : exposer `/procedures` (GET liste, GET détail, POST création).
- **Livrables** : router FastAPI, schémas Pydantic, intégration audit et cache.
- **Références** : `backend/app/api/`, `backend/app/main.py`.

## 5. Développer les endpoints d'exécution des procédures
- **Objectif** : gérer `/runs`, progression d'étapes et commits.
- **Livrables** : router FastAPI `/runs`, intégration FSM, gestion erreurs métier.
- **Références** : `backend/app/services/procedures/`, `backend/app/api/`.

## 6. Implémenter la validation typée des slots
- **Objectif** : valider les données collectées selon leur type et contraintes.
- **Livrables** : module `services/procedures/slots.py`, messages d'erreurs localisables.
- **Références** : schémas JSON `docs/json_schema_procedure_v*.json`.

## 7. Gestion des checklists dynamiques par étape
- **Objectif** : suivre la complétion des checklists au niveau des runs.
- **Livrables** : modèles ORM checklist + états, service de validation, exposition API.
- **Références** : `backend/app/models.py`, `backend/app/services/procedures/`.

## 8. Intégrer le cache Redis pour les procédures et exécutions
- **Objectif** : mettre en cache listes/détails pour réduire la latence.
- **Livrables** : utilisation `get_redis_client()`, invalidation cohérente, instrumentation.
- **Références** : `backend/app/cache.py`, `README.md`.

## 9. Écrire les tests unitaires pour FSM et slots
- **Objectif** : atteindre ≥ 80 % de couverture sur la logique procédurale.
- **Livrables** : tests Pytest ciblant transitions FSM et validation des slots.
- **Références** : `backend/tests/`, `pyproject.toml`.

## 10. Créer les tests d'intégration pour les endpoints procéduraux
- **Objectif** : garantir le parcours complet via l'API.
- **Livrables** : tests `TestClient` couvrant création de procédure, run et erreurs.
- **Références** : `backend/tests/integration/`.

## 11. Fournir une procédure de démonstration
- **Objectif** : proposer un scénario de bout en bout pour validation fonctionnelle.
- **Livrables** : fichier `docs/procedures/demo.json`, script de chargement, guide.
- **Références** : `docs/exemple_procedure_pilote.json`, `scripts/`.

## 12. Documenter les schémas et l'API
- **Objectif** : mettre à jour la documentation technique et OpenAPI.
- **Livrables** : schémas JSON actualisés, guide `docs/procedures.md`, descriptions API.
- **Références** : `docs/`, `backend/app/main.py` (OpenAPI).
