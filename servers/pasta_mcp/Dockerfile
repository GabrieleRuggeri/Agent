FROM python:3.12-slim

WORKDIR /app

RUN pip install "mcp[cli]>=1.27.2" "psycopg[binary]>=3.2"

COPY registry ./registry
COPY servers/pasta_mcp ./pasta_mcp

ENV PYTHONPATH=/app
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8001

WORKDIR /app/pasta_mcp

EXPOSE 8001

CMD ["python", "pasta_server.py"]
