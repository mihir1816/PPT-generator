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
RUN mkdir -p src/app && touch src/app/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

COPY . .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
