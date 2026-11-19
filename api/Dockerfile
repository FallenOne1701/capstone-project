# Support Desk API for Railway: Python 3.12 + Node 22 (MCP Server 1 runs as a stdio subprocess for Google writes).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Google tool (vendored MCP Server 1): build, then drop dev dependencies
COPY mcp_server/package.json mcp_server/package-lock.json mcp_server/tsconfig.json mcp_server/
RUN cd mcp_server && npm ci
COPY mcp_server/src mcp_server/src
RUN cd mcp_server && npm run build && npm prune --omit=dev

# Python dependencies first (read from pyproject.toml), so a code-only change reuses this layer and the model below
COPY pyproject.toml ./
RUN python -c "import tomllib; [print(d) for d in tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']]" \
      > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt

# Embedding model baked into the image so first boot doesn't download it
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# App code last; uvicorn imports `app` from /app (its working directory), so data files such as
# app/corpus/sources.yaml are read in place
COPY app app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
