# Dockerfile
FROM python:3.13-slim
WORKDIR /app

# System dependencies for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the limes_outpost package in editable mode so all containers
# can resolve `from limes_outpost.X import Y` correctly
COPY pyproject.toml .
COPY limes_outpost/ ./limes_outpost/
RUN pip install --no-cache-dir -e .

# Install Celery + Redis client (Phase 3)
RUN pip install --no-cache-dir "celery[redis]>=5.3" "redis>=5.0"

# Install FastAPI + uvicorn (Phase 4)
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29" "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7" "httpx>=0.27" "email-validator>=2.0"

# Copy source
COPY . .

# Default: CLI entrypoint
# Overridden per-service in docker-compose.yml
CMD ["python", "cli/main.py"]
