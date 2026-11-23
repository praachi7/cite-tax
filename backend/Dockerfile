# CiteTax API (FastAPI). Build context is the repository root: the API reads corpus/ and params/ at runtime,
# and backend/tests/engine/personas/ (the P1-P10 inputs served by GET /personas).
#   docker compose build api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    HF_HOME=/cache/huggingface

WORKDIR /app

# CPU-only PyTorch first (the default wheel pulls in CUDA), then the pinned requirements.
COPY requirements.txt requirements-api.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1 \
 && pip install -r requirements-api.txt

COPY params ./params
COPY corpus ./corpus
COPY backend ./backend
# Phase H measured results, served by GET /evaluation.
COPY eval/results ./eval/results

# BGE-M3 is downloaded on the first /ask into HF_HOME (a named volume in docker-compose.yml).
RUN useradd --create-home --uid 10001 citetax \
 && mkdir -p /cache/huggingface /app/build \
 && chown -R citetax /cache /app/build
USER citetax

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/personas', timeout=4)"
CMD ["uvicorn", "api.app:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
