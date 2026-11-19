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

# Python app (editable install so data files such as app/corpus/sources.yaml are read from /app)
COPY pyproject.toml ./
COPY app app
RUN pip install -e .

# Embedding model baked into the image so first boot doesn't download it
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
