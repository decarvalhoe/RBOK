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
  "actor": "demo-admin",
  "id": "proc_001_onboarding_client",
  "name": "Onboarding Client",
  "description": "Procédure d'accueil et d'enregistrement d'un nouveau client",
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

La réponse renvoie l’identifiant interne de chaque étape (`id`) qui servira lors de l’audit.

## 3. Lancer une exécution (« run »)

Créez un run en précisant l’acteur (utilisateur opérateur) :

```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "procedure_id": "proc_001_onboarding_client"}'
```

La réponse contient `id`, `state` et les timestamps. Conservez `id` pour les commits suivants.

## 4. Enregistrer les commits d’étapes

Chaque commit inclut `actor` (traçabilité), la charge utile collectée et la clé d’étape :

```bash
RUN_ID="<remplacer-par-l-id-du-run>"

curl -X POST "http://localhost:8000/runs/${RUN_ID}/steps/welcome/commit" \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "payload": {"client_name": "Jane Doe", "preferred_language": "français"}}'

curl -X POST "http://localhost:8000/runs/${RUN_ID}/steps/contact_info/commit" \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "payload": {"email": "jane.doe@example.com", "phone": "+41 79 123 45 67"}}'

curl -X POST "http://localhost:8000/runs/${RUN_ID}/steps/service_selection/commit" \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "payload": {"services_interested": "consultation", "budget_range": "1000-5000 CHF"}}'

curl -X POST "http://localhost:8000/runs/${RUN_ID}/steps/confirmation/commit" \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "payload": {"confirmation_accepted": true, "next_steps_scheduled": "2025-01-15"}}'

curl -X POST "http://localhost:8000/runs/${RUN_ID}/steps/completed/commit" \
  -H 'Content-Type: application/json' \
  -d '{"actor": "agent-qa", "payload": {"notes": "Client satisfait"}}'
```

La dernière étape clôture automatiquement le run (`state: completed`).

## 5. Vérifier l’audit trail (ALCOA+)

Les événements sont accessibles via `/audit-events`. Chaque action enregistre `actor` (Attributable), `occurred_at` (Horodatage lisible), `payload_diff` (Original/Accurate), et est scellée en base (Durable/Available).

### Procédure

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure&entity_id=proc_001_onboarding_client"
```

Résultat attendu : un événement `procedure.created` avec les métadonnées complètes de la procédure importée.

### Run

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure_run&entity_id=${RUN_ID}"
```

On y observe `run.created` puis `run.updated` (passage à `completed` avec `closed_at`).

### Étapes

```bash
curl "http://localhost:8000/audit-events?entity_type=procedure_run_step&entity_id=${RUN_ID}:confirmation"
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

Suivez ces commandes pour démontrer la conformité de la procédure pilote de bout en bout.
