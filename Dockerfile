# ReconcileAI -- single-origin production image.
#
# Builds the frontend, then serves it from the same FastAPI process that
# serves the API (backend/app/main.py mounts frontend/dist when present).
# One origin means no CORS configuration and no frontend-side API base URL
# are needed in production -- see the dated architectural decision in
# CLAUDE.md ("The frontend is React... calls the backend API directly").
#
# This image runs the demo exactly as documented: MockAIProvider (no LLM
# API key required), the synthetic 300-record dataset, SQLite. It performs
# no real financial mutation and makes no live Razorpay or LLM call unless
# those provider credentials are explicitly supplied as environment
# variables (see docs/provider-adapters.md, docs/ai-controller.md).

FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY shared/ shared/
COPY data/ data/
COPY --from=frontend-build /app/frontend/dist/ frontend/dist/

ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Render/Railway-style platforms inject $PORT; default to 8000 for a plain
# `docker run`. Binds 0.0.0.0 since the container's own loopback is not
# reachable from outside it.
EXPOSE 8000
CMD ["sh", "-c", "cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
