# PPT Template Reader

Reads a PowerPoint `.pptx` file and exports structured JSON describing the
template, slides, layouts, theme, media, fonts, and later detailed shape styles.

## Step 2: Inventory

Run:

```bash
python3 src/cli.py "/Users/sarrthakchauhan/Downloads/template-1 (4).pptx"
```

## OpenAI Content Generation

The generator can use OpenAI for slide writing while keeping the existing
rule-based generator as a fallback. By default it uses `gpt-5-nano` through
the OpenAI Responses API with structured JSON output.

Set your API key before starting the server:

```bash
export OPENAI_API_KEY="sk-..."
python3 server.py
```

For local development, you can also create a `.env` file from `.env.example`.
The server reads it automatically, and `.env` is ignored by git.

Useful environment variables:

```bash
OPENAI_MODEL=gpt-5-nano python3 server.py
OPENAI_MODEL=gpt-5-mini python3 server.py
DISABLE_OPENAI_GENERATOR=1 python3 server.py
OPENAI_TIMEOUT=60 python3 server.py
OPENAI_RETRIES=2 python3 server.py
OPENAI_MAX_OUTPUT_TOKENS=2600 python3 server.py
```

If `OPENAI_API_KEY` is missing or the request fails, generation still works
with the local rule-based content path. Placeholder values such as
`sk-your-key-here` are treated as missing keys. When the key exists but OpenAI
is unavailable, the API response includes `contentSource.source = "fallback"`
and the app shows that local rules were used.

To check whether the backend is ready for OpenAI without exposing secrets:

```bash
curl http://127.0.0.1:8000/api/status
```

For the hosted app, set these deployment variables:

```bash
# Render / backend
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-nano
DISABLE_OLLAMA_MAPPER=1

# Vercel / frontend
PPT_API_BASE_URL=https://prompt-on-ppt-api.onrender.com
```

## Optional Local AI Mapping

The app first builds a rule-based semantic map for every PPTX template. If
Ollama is running locally, it then asks Ollama to improve that map.

Install and run Ollama, then pull a local model:

```bash
ollama pull llama3.2
```

Start this app normally:

```bash
python3 server.py
```

When Ollama is unavailable, generation still works with the rule-based mapper.
The browser status will say either `rule mapping` or `ollama mapping`.

Useful environment variables:

```bash
OLLAMA_MODEL=llama3.2 python3 server.py
DISABLE_OLLAMA_MAPPER=1 python3 server.py
```

Deployment note: Vercel will not run local Ollama. For hosted deployment, keep
the same mapper interface but point it at a hosted model endpoint or backend
worker.

## Vercel Landing Page

The root page is the premium landing page:

```text
web/index.html
web/landing.css
web/landing.js
```

The generator UI is still available at:

```text
/app.html
```

Static Vercel hosting can serve the landing page and UI assets. The full PPTX
generation flow needs a hosted backend because it uses Python, PPTX ZIP/XML
editing, local files, Quick Look thumbnails on macOS, and optional Ollama. For
production, host the backend separately on a Python-friendly service such as
Render, Railway, Fly.io, or a VPS, then point the frontend API calls to that
backend.
