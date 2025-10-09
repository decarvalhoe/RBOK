# AI Gateway

The AI Gateway orchestrates interactions between the frontend experience, the procedural backend, and external AI providers. It exposes HTTP endpoints for automatic speech recognition (ASR), text-to-speech (TTS), large language model (LLM) chat completions, and utility "tools" that the assistant uses to coordinate procedure execution.

## Configuration

Configuration is managed through environment variables loaded via `ai_gateway.config.Settings`. The following variables are supported:

| Variable | Description | Default |
| --- | --- | --- |
| `AI_GATEWAY_OPENAI_API_KEY` / `OPENAI_API_KEY` | API key used for all OpenAI requests. | **Required** |
| `AI_GATEWAY_OPENAI_MODEL` | Default chat completion model used for `/llm/chat`. | `gpt-4o-mini` |
| `AI_GATEWAY_OPENAI_ASR_MODEL` | Model used for `/asr/transcriptions`. | `gpt-4o-mini-transcribe` |
| `AI_GATEWAY_OPENAI_TTS_MODEL` | Model used for `/tts/speech`. | `gpt-4o-mini-tts` |
| `AI_GATEWAY_OPENAI_TTS_VOICE` | Default voice preset for `/tts/speech` when the request omits one. | `alloy` |
| `AI_GATEWAY_BACKEND_BASE_URL` | Base URL for the procedural backend (used by tool endpoints). | `http://localhost:8000` |
| `AI_GATEWAY_ALLOWED_ORIGINS` | CSV list of origins allowed by CORS middleware. | `*` |

> **Note:** the service automatically falls back to the legacy `OPENAI_API_KEY` environment variable when `AI_GATEWAY_OPENAI_API_KEY` is not provided.

## Endpoint Contracts

### `POST /asr/transcriptions`

**Request:**

```json
{
  "audio_base64": "<base64 encoded audio>",
  "audio_format": "wav",
  "language": "fr"
}
```

**Response:**

```json
{
  "text": "transcribed text",
  "language": "fr",
  "confidence": 0.92
}
```

Performs automatic speech recognition via OpenAI Whisper models.

### `POST /tts/speech`

**Request:**

```json
{
  "text": "Bonjour",
  "voice": "alloy",
  "audio_format": "mp3"
}
```

**Response:**

```json
{
  "audio_base64": "<base64 audio>",
  "audio_format": "mp3",
  "voice": "alloy"
}
```

Generates speech audio using OpenAI TTS models.

### `POST /llm/chat`

**Request:**

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "model": "gpt-4o-mini",
  "temperature": 0.2,
  "max_tokens": 256
}
```

**Response:**

```json
{
  "content": "Hello, how can I help you today?",
  "model": "gpt-4o-mini",
  "finish_reason": "stop",
  "usage": {"total_tokens": 128}
}
```

Requests chat completions from OpenAI and normalises the response payload.

### Tool Endpoints

The following endpoints coordinate with the backend API to support slot collection during procedure runs:

* `POST /tools/get_required_slots` – Accepts `{ "procedure_id": "...", "step_key": "..." }` and returns `{ "slots": [ { "name": "email", ... } ] }`.
* `POST /tools/validate_slot` – Accepts `{ "procedure_id": "...", "step_key": "...", "slot_name": "...", "value": <any> }` and returns `{ "is_valid": true, "reason": null }`.
* `POST /tools/commit_step` – Accepts `{ "run_id": "...", "step_key": "...", "slots": { ... } }` and returns `{ "status": "committed", "run_state": "in_progress", ... }`.

All tool endpoints propagate backend errors as HTTP 502 responses, enabling the caller to react to upstream failures.

## Testing

Unit tests live under `ai_gateway/tests/` and rely on FastAPI's dependency overrides to mock external services. Run them with:

```bash
pytest ai_gateway/tests
```
