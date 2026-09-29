# Utilisation d'une image officielle Python 3.11 légère
FROM python:3.11-slim

# Définition du répertoire de travail dans le conteneur
WORKDIR /app

# Installation des dépendances système nécessaires pour certaines bibliothèques (compilation, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances Python en premier (optimisation du cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code source et des données dans le conteneur
COPY src/ ./src/

# Commande par défaut lancée lorsque le conteneur démarre
CMD ["python", "src/main.py"]