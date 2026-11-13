# Contracts API image (ADR-0025). Built in Azure Container Registry (az acr build), no local Docker needed.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY api/requirements-container.txt .
RUN pip install -r requirements-container.txt

# Only the code the API runs: no evaluation data, results, infra scripts or tests (.dockerignore)
COPY ingestion/pipeline ingestion/pipeline
COPY agents agents
COPY identity identity
COPY api api
# Approved taxonomy snapshot (ADR-0026): the API never connects to the database
COPY taxonomy/snapshots taxonomy/snapshots

# Run as a non-root user with no shell login
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000
# --no-server-header: do not advertise the server software (found during local testing)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
