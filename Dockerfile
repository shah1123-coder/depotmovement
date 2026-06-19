FROM ubuntu:22.04

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip curl gnupg2 apt-transport-https build-essential unixodbc unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 mssql-tools \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="$PATH:/opt/mssql-tools/bin"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
RUN python3.10 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3.10 -m pip install --no-cache-dir .
RUN cp -R /app/config /usr/local/lib/python3.10/config

CMD ["celery", "-A", "depot.celery.app:celery_app", "worker", "--loglevel=INFO"]
