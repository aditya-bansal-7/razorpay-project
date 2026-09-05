# Udhaar AI — Backend

Flask-based backend for Udhaar AI, a smart collections management system with Razorpay integration.

## Quick Start

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # Then fill in your values
python run.py
```

## API Health Check

```
GET /health              → General backend health
GET /api/ai/health       → AI integration status
```

---

## AI Integration

The backend includes a provider-independent AI integration layer that can be used to add LLM-powered features (e.g., smart collection strategies) without coupling to a specific vendor.

### Architecture

```
AIProvider (abstract base)
    ↓
GeminiProvider (Google Gemini implementation)
    ↑
get_ai_provider() (factory — returns the configured provider or None)
```

All AI code lives in `app/ai/`:

| File | Purpose |
|------|---------|
| `base.py` | Abstract `AIProvider` interface |
| `config.py` | `AIConfig` dataclass — reads env vars |
| `factory.py` | `get_ai_provider()` — returns provider or `None` |
| `exceptions.py` | Custom exception hierarchy |
| `providers/gemini.py` | Gemini SDK implementation |

### 1. Obtain a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key

### 2. Configure the Environment Variable

Add the key to your `.env` file:

```env
GEMINI_API_KEY=your-gemini-api-key-here
```

> **Never** commit `.env` or hardcode the key in source code.

### 3. Enable / Disable AI

AI is **enabled by default**. To disable it entirely:

```env
AI_ENABLED=false
```

When disabled (or when the API key is missing), the application continues to run normally — all existing features work without AI. The factory function `get_ai_provider()` simply returns `None`.

### 4. Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key |
| `AI_MODEL_NAME` | `gemini-2.0-flash` | Model to use |
| `AI_TIMEOUT` | `30` | Request timeout (seconds) |
| `AI_ENABLED` | `true` | Global on/off switch |

### 5. Usage Example

```python
from app.ai import get_ai_provider

provider = get_ai_provider()
if provider is not None:
    response = provider.generate(
        "Summarise this customer's payment history",
        system_prompt="You are a collections analyst.",
    )
    print(response)
else:
    print("AI is not configured — skipping")
```

For structured JSON output (future use):

```python
schema = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "reason": {"type": "string"},
    },
}
response = provider.generate(
    "What action should we take?",
    response_schema=schema,
)
```

### 6. Error Handling

All AI exceptions inherit from `AIError`:

```python
from app.ai.exceptions import AIError, AITimeoutError, AIProviderError

try:
    response = provider.generate("Hello")
except AITimeoutError:
    # Handle timeout specifically
    ...
except AIError:
    # Catch any AI-related error
    ...
```

### 7. Running AI Tests

The test suite is fully mocked — no real API calls are made:

```bash
# Run only the AI tests
pytest tests/test_ai.py -v

# Run the full test suite (includes existing + AI tests)
pytest tests/ -v
```

---

## Existing Features

- **Customer Management** — CRUD operations for customers
- **Ledger** — Credit/payment tracking with outstanding balance
- **Collection Tasks** — Deterministic expected-recovery strategy
- **Razorpay Payment Links** — Create and track payment links
- **Razorpay Webhooks** — Handle partial and full payment events
- **Simulation System** — Generate datasets, run strategies, evaluate performance
