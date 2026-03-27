FROM python:3.12-slim

WORKDIR /app

# System deps for curl_cffi (needs libcurl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Copy config + scripts
COPY config/ config/
COPY scripts/ scripts/
COPY docs/ docs/

# Data volume for SQLite DB persistence
VOLUME /app/data

# Dashboard port
EXPOSE 8000

# Run bot in continuous mode (scanner + dashboard)
CMD ["python", "-m", "resell_bot"]
