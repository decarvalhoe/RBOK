# Guide de démonstration des procédures

Ce tutoriel explique comment charger la procédure pilote fournie dans `docs/exemple_procedure_pilote.json`, lancer une exécution complète via l’API FastAPI et vérifier l’audit trail (ALCOA+).

## 1. Pré-requis

- Le backend doit être démarré localement (par exemple `uvicorn app.main:app --reload`).
- L’API est supposée accessible sur `http://localhost:8000`.
- Python 3.10+ est disponible pour lancer le script d’import.

## 2. Importer la procédure pilote

Utilisez le script utilitaire pour transformer le JSON « pilote » et le pousser sur l’API :

```bash
python scripts/load_demo_procedure.py \
  --base-url http://localhost:8000 \
  --source docs/exemple_procedure_pilote.json \
  --actor demo-admin
```

Le script renvoie le document créé avec les `id` générés pour les étapes. L’import peut également être réalisé directement avec `curl` :

```bash
curl -X POST http://localhost:8000/procedures \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "id": "proc_001_onboarding_client",
  "name": "Onboarding Client",
  "description": "Procédure d'accueil et d'enregistrement d'un nouveau client",
  "metadata": {
    "category": "onboarding"
  },
  "steps": [
    {
      "key": "welcome",
      "title": "Accueil du client",
      "prompt": "Accueillez chaleureusement le nouveau client et expliquez-lui le processus d'onboarding.",
      "slots": [
        {"name": "client_name", "type": "string", "required": true, "validate": "^[A-Za-zÀ-ÿ\\s]{2,50}$"},
        {"name": "preferred_language", "type": "enum", "required": true, "options": ["français", "anglais", "allemand", "italien"]}
      ],
      "position": 0
    },
    {
      "key": "contact_info",
      "title": "Informations de contact",
      "prompt": "Collectez les informations de contact essentielles du client.",
      "slots": [
        {"name": "email", "type": "email", "required": true, "validate": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"},
        {"name": "phone", "type": "phone", "required": true, "mask": "+41 XX XXX XX XX"},
        {"name": "address", "type": "string", "required": false}
      ],
      "position": 1
    },
    {
      "key": "service_selection",
      "title": "Sélection des services",
      "prompt": "Aidez le client à choisir les services qui correspondent à ses besoins.",
      "slots": [
        {"name": "services_interested", "type": "enum", "required": true, "options": ["consultation", "formation", "support_technique", "audit"]},
        {"name": "budget_range", "type": "enum", "required": false, "options": ["< 1000 CHF", "1000-5000 CHF", "5000-10000 CHF", "> 10000 CHF"]}
      ],
      "position": 2
    },
    {
      "key": "confirmation",
      "title": "Confirmation et finalisation",
      "prompt": "Récapitulez les informations collectées et confirmez avec le client.",
      "slots": [
        {"name": "confirmation_accepted", "type": "boolean", "required": true},
        {"name": "next_steps_scheduled", "type": "date", "required": false}
      ],
      "position": 3
    },
    {
      "key": "completed",
      "title": "Onboarding terminé",
      "prompt": "Remerciez le client et fournissez les informations de suivi.",
      "slots": [],
      "position": 4
    }
  ]
}
JSON
```

Réponse attendue (`201 Created`) :

```json
{
  "id": "proc_001_onboarding_client",
  "name": "Onboarding Client",
  "description": "Procédure d'accueil et d'enregistrement d'un nouveau client",
  "metadata": {
    "category": "onboarding"
  },
  "steps": [
    {
      "id": "step_01HZY5KD1D2C3M4N5P6Q7R8S9T",
      "key": "welcome",
      "title": "Accueil du client",
      "prompt": "Accueillez chaleureusement le nouveau client et expliquez-lui le processus d'onboarding.",
      "position": 0,
      "metadata": {},
      "slots": [
        {"name": "client_name", "type": "string", "required": true, "label": null, "description": null, "validate": "^[A-Za-zÀ-ÿ\\s]{2,50}$", "mask": null, "options": null, "position": 0, "metadata": {}}
      ],
      "checklists": []
    }
  ]
}
```

Les autres étapes de la procédure sont retournées de la même manière. La réponse renvoie l’identifiant interne de chaque étape (`id`) qui servira lors de l’audit.

## 3. Lancer une exécution (« run »)

Créez un run en précisant l’opérateur concerné via `user_id` (facultatif si l’identifiant peut être dérivé du jeton d’authentification) :

```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"procedure_id": "proc_001_onboarding_client", "user_id": "agent-qa"}'
```

Réponse attendue (`201 Created`) :

```json
{
  "id": "run_01HZY5M0ZK7A1XTB7JH3G5C8K2",
  "procedure_id": "proc_001_onboarding_client",
  "user_id": "agent-qa",
  "state": "pending",
  "created_at": "2025-01-14T08:52:12.486193Z",
  "closed_at": null,
  "step_states": [],
  "checklist_states": []
}
```

Conservez `id` pour les commits suivants.

## 4. Enregistrer les commits d’étapes

L’API expose désormais un point d’entrée unique `POST /runs/{id}/commit-step` qui reçoit la clé de l’étape, les valeurs saisies (`slots`) et, le cas échéant, l’état de la checklist. Dès que la variante `POST /runs/{id}/steps/{key}/commit` sera en production, la structure de la charge utile et des réponses restera identique.

```bash
curl -X POST "http://localhost:8000/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{
        "step_key": "welcome",
        "slots": {
          "client_name": "Jane Doe",
          "preferred_language": "français"
        },
        "checklist": []
      }'
```

Réponse attendue (`200 OK`) :

```json
{
  "id": "run_01HZY5M0ZK7A1XTB7JH3G5C8K2",
  "procedure_id": "proc_001_onboarding_client",
  "user_id": "agent-qa",
  "state": "in_progress",
  "created_at": "2025-01-14T08:52:12.486193Z",
  "closed_at": null,
  "step_states": [
    {
      "step_key": "welcome",
      "payload": {
        "slots": {
          "client_name": "Jane Doe",
          "preferred_language": "français"
        },
        "checklist": []
      },
      "committed_at": "2025-01-14T08:55:01.124305Z"
    }
  ],
  "checklist_states": []
}
```

Pour les étapes suivantes, adaptez simplement `step_key`, les `slots` et la `checklist`. Une fois la dernière étape validée, la réponse inclura `"state": "completed"` et un `closed_at` renseigné.

### Script complet (curl)

Le bloc ci-dessous enchaîne l’import de la procédure (si elle n’existe pas déjà), la création du run, la validation de deux étapes et la consultation de l’audit trail. Ajustez `BASE_URL` au besoin. (`jq` est requis pour extraire les réponses JSON.)

```bash
bash <<'DEMO'
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"

curl -sS -X POST "${BASE_URL}/procedures" \
  -H 'Content-Type: application/json' \
  -d @docs/exemple_procedure_pilote.json >/dev/null

RUN_ID=$(curl -sS -X POST "${BASE_URL}/runs" \
  -H 'Content-Type: application/json' \
  -d '{"procedure_id": "proc_001_onboarding_client", "user_id": "agent-qa"}' | jq -r '.id')

curl -sS -X POST "${BASE_URL}/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{"step_key": "welcome", "slots": {"client_name": "Jane Doe", "preferred_language": "français"}, "checklist": []}' | jq '.'

curl -sS -X POST "${BASE_URL}/runs/${RUN_ID}/commit-step" \
  -H 'Content-Type: application/json' \
  -d '{"step_key": "contact_info", "slots": {"email": "jane.doe@example.com", "phone": "+41 79 123 45 67"}, "checklist": []}' >/dev/null

curl -sS "${BASE_URL}/audit-events?entity_type=procedure_run&entity_id=${RUN_ID}" | jq '.'
DEMO
```

## 5. Vérifier l’audit trail (ALCOA+)

Les événements sont accessibles via `/audit-events`. Chaque action enregistre `actor` (Attributable), `occurred_at` (Horodatage lisible), `payload_diff` (Original/Accurate), et est scellée en base (Durable/Available).

### Procédure

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure&entity_id=proc_001_onboarding_client"
```

Résultat attendu : un événement `procedure.created` avec les métadonnées complètes de la procédure importée.

```json
[
  {
    "id": "evt_01HZY5P92G3G1PPWEF8Z4CMX2B",
    "type": "procedure.created",
    "entity_type": "procedure",
    "entity_id": "proc_001_onboarding_client",
    "actor": "demo-admin",
    "occurred_at": "2025-01-14T08:50:05.912384Z",
    "payload_diff": {
      "after": {
        "id": "proc_001_onboarding_client",
        "name": "Onboarding Client",
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
    "id": "evt_01HZY5QDY90NBJ4R26F6FH2SNQ",
    "type": "run.created",
    "entity_type": "procedure_run",
    "entity_id": "run_01HZY5M0ZK7A1XTB7JH3G5C8K2",
    "actor": "agent-qa",
    "occurred_at": "2025-01-14T08:52:12.512009Z",
    "payload_diff": {
      "after": {
        "state": "pending",
        "procedure_id": "proc_001_onboarding_client",
        "user_id": "agent-qa"
      }
    }
  },
  {
    "id": "evt_01HZY5QFJ8R31CFVC1T34ZC8DJ",
    "type": "run.updated",
    "entity_type": "procedure_run",
    "entity_id": "run_01HZY5M0ZK7A1XTB7JH3G5C8K2",
    "actor": "agent-qa",
    "occurred_at": "2025-01-14T08:59:42.101776Z",
    "payload_diff": {
      "before": {
        "state": "in_progress",
        "closed_at": null
      },
      "after": {
        "state": "completed",
        "closed_at": "2025-01-14T08:59:42.097634Z"
      }
    }
  }
]
```

### Étapes

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure_run_step&entity_id=${RUN_ID}:confirmation"
```

Chaque commit produit un événement `run.step_committed` contenant l’état avant/après (pour les re-soumissions) et la charge utile saisie. Ce journal répond aux critères ALCOA+ :

- **Attributable** – champ `actor`.
- **Legible** – JSON structuré, timestamps ISO.
```json
[
  {
    "id": "evt_01HZY5QGN6Q9YH4VZ88A1YQ4TE",
    "type": "run.step_committed",
    "entity_type": "procedure_run_step",
    "entity_id": "run_01HZY5M0ZK7A1XTB7JH3G5C8K2:confirmation",
    "actor": "agent-qa",
    "occurred_at": "2025-01-14T08:58:17.440512Z",
    "payload_diff": {
      "after": {
        "payload": {
          "slots": {
            "confirmation_accepted": true,
            "next_steps_scheduled": "2025-01-15"
          },
          "checklist": []
        },
        "committed_at": "2025-01-14T08:58:17.437211Z"
      }
    }
  }
]
```
- **Contemporaneous** – `occurred_at` généré lors de la requête.
- **Original** – `payload_diff.after` contient la donnée brute.
- **Accurate** – intégrité assurée par la base et les validations.
- **Complete** – chaque transition est tracée.
- **Consistent** – les états sont ordonnés chronologiquement.
- **Enduring** – persistance en base relationnelle.
- **Available** – exposition via l’API pour revue/audit.

Suivez ces commandes pour démontrer la conformité de la procédure pilote de bout en bout.
