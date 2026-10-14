# Cloud Run runs a container; this is the one image the API ships as.
# Single stage, slim base, no build tools — the app has no compiled deps.
FROM python:3.12-slim

# Don't write .pyc files, don't buffer stdout (so Cloud Logging sees lines immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps from the manifest first so this layer caches across code changes.
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
RUN pip install .

# The installed package (site-packages) has no fixed path relationship to
# this directory once pip install copies files out of src/, so migrate.py
# needs to be told explicitly where the SQL files ended up.
ENV MIGRATIONS_DIR=/app/migrations

# Run as a non-root user; Cloud Run does not require it but least privilege applies in the container too.
RUN useradd --create-home --uid 1000 app
USER app

# Cloud Run injects $PORT (default 8080). uvicorn must bind 0.0.0.0, not localhost.
# One image, two services (ADR 0034): APP_MODULE picks the entry point. The API
# runs the default; the worker service sets anyview.worker:app. An env var
# rather than a command override, because Terraform creates each service with
# a placeholder image that would not understand the override.
ENV APP_MODULE=anyview.main:app
EXPOSE 8080
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT:-8080}"]
