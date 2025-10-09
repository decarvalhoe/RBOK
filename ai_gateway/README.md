# Réalisons AI Gateway

## Variables d'environnement

| Nom | Description | Valeur par défaut | Recommandations |
| --- | ----------- | ----------------- | ---------------- |
| `AI_GATEWAY_OPENAI_API_KEY` | Clé API OpenAI utilisée pour les appels LLM/ASR/TTS. | *(obligatoire)* | Stocker dans un secret manager, activer la rotation et limiter les droits sur l'organisation OpenAI. |
| `AI_GATEWAY_OPENAI_MODEL` | Modèle principal pour les complétions. | `gpt-4o-mini` | Adapter selon les besoins, prévoir une stratégie de fallback. |
| `AI_GATEWAY_OPENAI_ASR_MODEL` | Modèle pour la transcription audio. | `gpt-4o-mini-transcribe` | Vérifier la disponibilité et surveiller les quotas. |
| `AI_GATEWAY_OPENAI_TTS_MODEL` | Modèle pour la synthèse vocale. | `gpt-4o-mini-tts` | Mettre à jour si une voix spécifique est requise. |
| `AI_GATEWAY_OPENAI_TTS_VOICE` | Voix par défaut. | `alloy` | Limiter aux voix autorisées pour votre cas d'usage. |
| `AI_GATEWAY_BACKEND_BASE_URL` | URL du backend FastAPI. | `http://localhost:8000` | Doit pointer vers un endpoint sécurisé (HTTPS) en production. |
| `AI_GATEWAY_ALLOWED_ORIGINS` | Origines autorisées pour le CORS. | `http://localhost:3000` | Restreindre aux domaines approuvés, réviser à chaque nouvelle application cliente. |

### Bonnes pratiques
- Copier `.env.example` vers `.env` et définir des valeurs propres à chaque environnement.
- La fonction `get_settings()` déclenche une erreur si aucune clé OpenAI n'est fournie, assurant un fail-fast au démarrage ou via `/healthz`.
- Définir des clés différentes pour les environnements staging / production et documenter la rotation.

## Démarrage local
```bash
cp .env.example .env
# éditer .env
uvicorn ai_gateway.main:app --reload --port 8010
```

Le point d'extrémité `/healthz` renvoie `{ "status": "ok" }` lorsque la configuration est correcte.
