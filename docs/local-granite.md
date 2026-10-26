# Local Granite explanation experiment

## Boundary

Granite paraphrases an existing exception result. It does not perform the
reconciliation, investigate with tools, change decisions, edit records, or write
audit events. The original MockAIProvider investigation remains unchanged.
All examples and evaluation records use the repository's synthetic dataset.
This is local IBM Granite through Ollama, not IBM Bob or watsonx.

## Setup

Use Python 3.12 and Node 22. From this separate checkout:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend
npm ci
```

Ollama must already be running with `granite4:3b` installed. The app checks
`/api/tags`, but never downloads a model or loads one during a status check.
The model is already installed on the development Mac used for this change.

Backend, from the repository root:

```sh
GRANITE_ENABLED=1 ENVIRONMENT=development .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Frontend, in another terminal:

```sh
cd frontend
VITE_GRANITE_ENABLED=1 npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173, start a synthetic run, open Work Queue and then an
exception. The explanation panel sits below Financial Summary. Generation starts
only on a button click. Cancel disconnects the request; the backend cancels its
HTTP operation and releases the inference slot (provider resource release can
lag until Ollama observes the disconnect). Navigation clears the component and
discards late results.

Never expose these development servers through a tunnel or reverse proxy.
The backend rejects non-loopback peers, unexpected Hosts/Origins, forwarded
headers and cross-site browser requests. This is a local boundary, not user
authentication. Existing actor capability checks are not enterprise IAM.

## Interfaces

- `GET /granite/status`: local connectivity/model check, no inference.
- `POST /exceptions/{id}/granite-explanation`: empty body, no query parameters.
  Server retrieves the exception; browser-supplied facts/prompts are rejected.
- Response: explanation, referenced fact IDs, model, source, elapsed milliseconds,
  snapshot fingerprint, fallback reason and optional model-load milliseconds.
- Busy inference: 429. Missing exception: 404. Disabled/production feature: 404.
- These experimental endpoints are excluded from public OpenAPI documentation.

Snapshot construction reuses `build_explanation`; it does not recalculate money.
The prompt is deliberately smaller than the snapshot: it receives plain-English
statements for classification, hypothesis-verification scope, policy outcome and
approval flag, plus the exact decision label. Amounts and raw rule codes remain
in the authoritative UI and server snapshot, not the model prompt. Identifiers,
raw records, unverified hypothesis prose, credentials and notes are excluded.
Logs do not include prompts or outputs. Explanations are not persisted.

The fixed adapter calls `http://127.0.0.1:11434/api/chat` using existing httpx.
Settings: context 2048, output 256 tokens, temperature 0, keep-alive 60 seconds,
non-streaming schema output, 120-second overall deadline and one inference slot.
No automatic provider/model substitution exists.

Validation checks schema, exact decision, allowlisted references, text bounds,
numeric claims (Decimal comparison against supplied amounts), ASCII English and
selected contradictory phrases. Authoritative values remain separately visible. JSON
schema and phrase checks **cannot prove semantic accuracy**. Read every AI answer
against the original facts. Provider/validation failure yields explicitly labelled
deterministic fallback text, never an AI success claim.

## Why this architecture

1. **Deterministic code owns mathematics:** a language model can describe a fee
   mismatch, but must not decide whether money matches or a case is safe.
2. **Adapter owns inference:** a small isolated module contains network/model
   dependencies; model failures cannot alter the existing decision pipeline.
3. **Evaluation owns quality claims:** well-formed JSON can still misunderstand
   a rejected hypothesis or a required approval. Successful HTTP calls and valid
   JSON are not accuracy measurements.

## Verification

```sh
.venv/bin/python -m pytest -q
cd frontend
npm test
npm run build
npm run test:e2e
```

Existing E2E tests expect the local backend and Vite frontend already running.
The production build strips the development panel even if the frontend flag is
set. The backend must remain disabled in any production environment; nothing in
this change modifies Railway or its deployed settings.

Run model evaluation from the root, without other inference clients:

```sh
.venv/bin/python scripts/evaluate_granite.py
```

The script uses a temporary synthetic database, ten fixed scenario categories,
three repetitions each, and records raw model responses for review separately
from accepted/fallback UI results. It writes `docs/granite-evaluation-results.json`.
Raw outputs here are synthetic evaluation artifacts only, never runtime logs.
Human review fields intentionally start null; no automatic accuracy score is
invented. See `granite-evaluation.md` for the reviewed measured result.
