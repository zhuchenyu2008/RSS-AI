FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on

WORKDIR /app

# System deps (optional: ca-certificates, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install requirements first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy application
COPY . /app/

RUN chmod +x /app/run.sh && mkdir -p /app/logs /app/data

EXPOSE 3601

CMD ["/bin/bash", "/app/run.sh"]
