FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# Enforce pyasn1 pin before/with install — >=0.6.1 breaks pysnmp (silent SNMP failure).
RUN pip install --upgrade pip \
    && pip install "pyasn1>=0.4.8,<0.6.1" \
    && pip install .

EXPOSE 8000

CMD ["uvicorn", "netatlas.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
