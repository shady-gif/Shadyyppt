# PPT Template Reader

Reads a PowerPoint `.pptx` file and exports structured JSON describing the
template, slides, layouts, theme, media, fonts, and later detailed shape styles.

## Step 2: Inventory

Run:

```bash
python3 src/cli.py "/Users/sarrthakchauhan/Downloads/template-1 (4).pptx"
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
