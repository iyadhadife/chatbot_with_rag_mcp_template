FROM python:3.10-slim

WORKDIR /app

# Installation des dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances du serveur MCP
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source et de la pipeline RAG
COPY src/ /app/src/

# Exposition du port du serveur MCP (si mode HTTP/SSE)
EXPOSE 8001

# Lancement du serveur MCP
CMD ["python", "src/mcp_server.py"]