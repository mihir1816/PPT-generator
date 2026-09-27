FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl libgl1 libglib2.0-0 \
    poppler-utils libmagic1 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install deps in a layer keyed only on pyproject.toml, so editing app code
# doesn't invalidate this (expensive) layer on rebuild. setuptools needs the
# `src` package-discovery root to exist at install time for an editable
# install; a stub satisfies that without pulling in real source (which is
# copied in afterward and overrides the stub via the editable path mapping).
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p src/app && touch src/app/__init__.py \
    && pip install --timeout 300 --retries 5 -e .

COPY . .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Pre-download the embedding model during build so it is available immediately
# at runtime without any network call. The cache dir matches the volume mount
# in docker-compose.yml (tcg_fastembed_cache → /root/.cache/fastembed).
RUN python - <<'EOF'
from fastembed import TextEmbedding
# Download and cache the model; this runs once at build time
list(TextEmbedding("nomic-ai/nomic-embed-text-v1.5").embed(["warmup"]))
print("Embedding model pre-downloaded OK")
EOF

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
