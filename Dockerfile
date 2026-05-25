FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_HOST=0.0.0.0 \
    PORT=8080 \
    GENERATE_DEMO_DATA=true

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pipeline ./pipeline
COPY mcp_server ./mcp_server
COPY client ./client
COPY deploy ./deploy
COPY data/raw/.gitkeep ./data/raw/.gitkeep
COPY data/processed/.gitkeep ./data/processed/.gitkeep
COPY output/.gitkeep ./output/.gitkeep

RUN pip install --upgrade pip && pip install .

EXPOSE 8080

CMD ["python", "-m", "deploy.start_http"]
