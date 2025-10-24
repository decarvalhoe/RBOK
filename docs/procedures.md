# Guide de démonstration des procédures

Ce tutoriel explique comment charger la procédure de démonstration fournie dans [`docs/procedures/demo.json`](docs/procedures/demo.json), lancer une exécution complète via l’API FastAPI et vérifier l’audit trail (ALCOA+).

## 1. Pré-requis

- Le backend doit être démarré localement (par exemple `uvicorn app.main:app --reload`).
- L’API est supposée accessible sur `http://localhost:8000`.
- Python 3.10+ est disponible pour lancer le script d’import.

## 2. Procédure de démonstration : « Rétablissement d'un réseau d'agence »

Le fichier [`docs/procedures/demo.json`](docs/procedures/demo.json) décrit un incident réseau critique pour une agence bancaire. Il illustre les fonctionnalités de collecte de slots structurés, de suivi de checklists et de métadonnées enrichies.

### Métadonnées globales

- `category` : `incident_response`
- `business_unit` : `operations`
- `audience` : `soc`, `it_ops`, `audit`
- `version` : `1.0-demo`
- `sla_minutes` : `90`

### Étapes & artefacts

| Étape (`key`) | Objectif | Slots principaux | Checklists |
|---------------|----------|-----------------|------------|
| `trigger` | Capturer l’alerte SOC | `incident_id`, `detection_timestamp`, `severity`, `reporting_channel` | `acknowledged`, `stakeholders_notified` |
| `diagnosis` | Qualifier l’impact | `impacted_sites`, `primary_symptom`, `customer_impact`, `sla_breach_expected` | `monitoring_checked`, `backup_links_tested` |
| `remediation` | Documenter l’action correctrice | `change_ticket`, `start_time`, `fix_applied`, `rollback_plan_available` | `change_approved`, `communication_sent` |
| `validation` | Confirmer le rétablissement | `service_status`, `validation_timestamp`, `residual_issues`, `next_follow_up` | `end_to_end_tests`, `monitoring_normalized` |
| `closure` | Clore et capitaliser | `final_state`, `postmortem_required`, `postmortem_date`, `lessons_learned` | `documentation_updated`, `sla_report_sent` |

Chaque étape inclut également des métadonnées (ex. `owner`, `channel`, `requires_change_ticket`) afin de montrer la persistance de données libres aux côtés des champs normés.

## 3. Importer la procédure de démonstration

### Avec le script utilitaire

Le script [`scripts/load_demo_procedure.py`](../scripts/load_demo_procedure.py) utilise désormais `docs/procedures/demo.json` par défaut et conserve les métadonnées/checklists du fichier source.

```bash
python scripts/load_demo_procedure.py \
  --base-url http://localhost:8000 \
  --actor demo-admin
```

### Import direct avec `curl`

Pour importer le JSON directement, ajoutez simplement le champ `actor` autour du fichier source :

```bash
ACTOR="demo-admin"
BASE_URL="${BASE_URL:-http://localhost:8000}"

curl -X POST "${BASE_URL%/}/procedures" \
  -H 'Content-Type: application/json' \
  -d "$(jq --arg actor "$ACTOR" '. + {actor: $actor}' docs/procedures/demo.json)"
```

### Réponse attendue (`201 Created`)

La réponse renvoie le document créé avec positions normalisées et identifiants générés pour les étapes. Extrait du premier élément :

```json
{
  "id": "proc_demo_retablissement_reseau",
  "name": "Démo – Rétablissement d'un réseau d'agence",
  "metadata": {
    "category": "incident_response",
    "business_unit": "operations"
  },
  "steps": [
    {
      "id": "step_01J0XYZ8N6FM3H4PK5R6S7T8U9",
      "key": "trigger",
      "title": "Déclenchement de l'incident",
      "prompt": "Recueillez les informations de base sur l'alerte réseau transmise par le SOC.",
      "position": 0,
      "metadata": {
        "owner": "soc",
        "channel": "pagerduty"
      },
      "slots": [
        {"name": "incident_id", "type": "string", "required": true, "label": "Identifiant d'incident", "position": 0}
      ],
      "checklists": [
        {"key": "acknowledged", "label": "Alerte confirmée par le SOC", "required": true, "position": 0}
      ]
    }
  ]
}
```

Les autres étapes conservent leurs métadonnées, slots et checklists respectifs.

## 4. Lancer une exécution (« run »)

Créez un run en précisant l’opérateur concerné via `user_id` (facultatif si l’identifiant peut être dérivé du jeton d’authentification) :

```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"procedure_id": "proc_demo_retablissement_reseau", "user_id": "agent-qa"}'
```

Réponse attendue (`201 Created`) :

```json
{
  "id": "run_01J0YZ4DGCE1A2B3C4D5E6F7G8",
  "procedure_id": "proc_demo_retablissement_reseau",
  "user_id": "agent-qa",
  "state": "pending",
  "created_at": "2025-02-18T08:52:12.486193Z",
  "closed_at": null,
  "step_states": [],
  "checklist_states": []
}
```

Conservez `id` pour les commits suivants.

## 5. Enregistrer les commits d’étapes

L’API expose un point d’entrée unique `POST /runs/{id}/commit-step` qui reçoit la clé de l’étape, les valeurs saisies (`slots`) et l’état de la checklist. Exemple pour la première étape (`trigger`) :

```bash
RUN_ID="run_01J0YZ4DGCE1A2B3C4D5E6F7G8"

curl -X POST "http://localhost:8000/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{
        "step_key": "trigger",
        "slots": {
          "incident_id": "INC-450123",
          "detection_timestamp": "2025-02-18",
          "severity": "critique",
          "reporting_channel": "monitoring"
        },
        "checklist": ["acknowledged", "stakeholders_notified"]
      }'
```

Réponse attendue (`200 OK`) :

```json
{
  "id": "run_01J0YZ4DGCE1A2B3C4D5E6F7G8",
  "procedure_id": "proc_demo_retablissement_reseau",
  "user_id": "agent-qa",
  "state": "in_progress",
  "step_states": [
    {
      "step_key": "trigger",
      "payload": {
        "slots": {
          "incident_id": "INC-450123",
          "detection_timestamp": "2025-02-18",
          "severity": "critique",
          "reporting_channel": "monitoring"
        },
        "checklist": ["acknowledged", "stakeholders_notified"]
      },
      "committed_at": "2025-02-18T08:55:01.124305Z"
    }
  ]
}
```

Pour les étapes suivantes, adaptez `step_key`, les `slots` et la `checklist`. La dernière étape (`closure`) retournera `"state": "completed"` avec un `closed_at` renseigné.

### Script complet (curl)

Le bloc ci-dessous enchaîne l’import de la procédure (si elle n’existe pas déjà), la création du run, la validation de deux étapes et la consultation de l’audit trail. Ajustez `BASE_URL` au besoin (`jq` est requis pour extraire les réponses JSON).

```bash
bash <<'DEMO'
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"
ACTOR="demo-admin"

curl -sS -X POST "${BASE_URL%/}/procedures" \
  -H 'Content-Type: application/json' \
  -d "$(jq --arg actor "$ACTOR" '. + {actor: $actor}' docs/procedures/demo.json)" >/dev/null || true

RUN_ID=$(curl -sS -X POST "${BASE_URL%/}/runs" \
  -H 'Content-Type: application/json' \
  -d '{"procedure_id": "proc_demo_retablissement_reseau", "user_id": "agent-qa"}' | jq -r '.id')

curl -sS -X POST "${BASE_URL%/}/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{"step_key": "trigger", "slots": {"incident_id": "INC-450123", "detection_timestamp": "2025-02-18", "severity": "critique", "reporting_channel": "monitoring"}, "checklist": ["acknowledged", "stakeholders_notified"]}' | jq '.'

curl -sS -X POST "${BASE_URL%/}/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{"step_key": "diagnosis", "slots": {"impacted_sites": "Agence Genève", "primary_symptom": "perte_connectivite", "customer_impact": "guichet_ferme", "sla_breach_expected": true}, "checklist": ["monitoring_checked"]}' >/dev/null

curl -sS "${BASE_URL%/}/audit-events?entity_type=procedure_run&entity_id=${RUN_ID}" | jq '.'
DEMO
```

## 6. Vérifier l’audit trail (ALCOA+)

Les événements sont accessibles via `/audit-events`. Chaque action enregistre `actor` (Attributable), `occurred_at` (Horodatage lisible), `payload_diff` (Original/Accurate) et est scellée en base (Durable/Available).

### Procédure

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure&entity_id=proc_demo_retablissement_reseau"
```

Résultat attendu : un événement `procedure.created` avec les métadonnées complètes de la procédure importée.

```json
[
  {
    "id": "evt_01J0YZJX3AM8N9PQRS0T1UVW2",
    "type": "procedure.created",
    "entity_type": "procedure",
    "entity_id": "proc_demo_retablissement_reseau",
    "actor": "demo-admin",
    "occurred_at": "2025-02-18T08:50:05.912384Z",
    "payload_diff": {
      "after": {
        "id": "proc_demo_retablissement_reseau",
        "name": "Démo – Rétablissement d'un réseau d'agence",
        "step_count": 5
      }
    }
  }
]
```

### Run

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure_run&entity_id=${RUN_ID}"
```

On y observe `run.created` puis `run.updated` (passage à `completed` avec `closed_at`).

```json
[
  {
    "id": "evt_01J0YZK0H3S4T5U6V7W8X9Y0Z",
    "type": "run.created",
    "entity_type": "procedure_run",
    "entity_id": "run_01J0YZ4DGCE1A2B3C4D5E6F7G8",
    "actor": "agent-qa",
    "occurred_at": "2025-02-18T08:52:12.512009Z",
    "payload_diff": {
      "after": {
        "state": "pending",
        "procedure_id": "proc_demo_retablissement_reseau",
        "user_id": "agent-qa"
      }
    }
  }
]
```

### Étapes

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure_run_step&entity_id=${RUN_ID}:remediation"
```

Chaque commit produit un événement `run.step_committed` contenant l’état avant/après (pour les re-soumissions) et la charge utile saisie. Ce journal répond aux critères ALCOA+ :

- **Attributable** – champ `actor`.
- **Legible** – JSON structuré, timestamps ISO.
- **Contemporaneous** – `occurred_at` généré lors de la requête.
- **Original** – `payload_diff.after` contient la donnée brute.
- **Accurate** – intégrité assurée par la base et les validations.
- **Complete** – chaque transition est tracée.
- **Consistent** – les états sont ordonnés chronologiquement.
- **Enduring** – persistance en base relationnelle.
- **Available** – exposition via l’API pour revue/audit.

Suivez ces commandes pour démontrer la conformité du scénario de bout en bout décrit dans le backlog.
