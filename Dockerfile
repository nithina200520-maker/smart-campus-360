# ==============================================================================
# SMART CAMPUS 360 - Docker Image (introduced in Phase 2)
# Stack: Flask 3 + SQLAlchemy + OpenCV/scikit-learn (single-app image)
# NOTE: .env, instance/ and other local state are excluded via .dockerignore
#       and are bind-mounted at runtime instead (see compose.yaml).
# ==============================================================================
FROM python:3.12-slim

# System library required by opencv-python-headless at runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (Phase 1 code is used as-is, no refactoring)
COPY . .

EXPOSE 5000

# Gunicorn WSGI server serving the module-level `app` from run.py
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "run:app"]
