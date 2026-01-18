# Expert Linux - Chatbot RAG avec MCP & Ollama

Ce projet implémente un assistant intelligent spécialisé dans l'administration système Linux. Il repose sur une architecture moderne utilisant le protocole **MCP (Model Context Protocol)** pour connecter un modèle d'IA local à une base de connaissances personnalisée (RAG).



## Fonctionnalités
- **RAG Local** : Interroge une base de données de commandes Linux sans envoyer de données dans le cloud.
- **Protocole MCP** : Utilise `FastMCP` pour exposer les outils de recherche via un serveur SSE.
- **Streaming** : Affichage de la réponse en temps réel (mot par mot) dans le terminal.
- **Agentic Design** : Comportement de l'expert défini via un fichier `linux_expert.md` modulaire.

---

## Architecture du Projet

```text
.
├── src/
│   ├── main.py                # Point d'entrée (Client Agent)
│   ├── linux_expert.md        # Identité et règles de l'agent
│   ├── chat_engine/
│   │   └── generate_answer.py # Logique de streaming et appels RAG
│   ├── mcp_server/
│   │   └── server.py          # Serveur MCP (FastAPI + SSE)
│   └── rag_engine/
│       ├── ingest.py          # Script d'indexation des données
│       └── retriever.py       # Logique de recherche documentaire
├── data/
│   └── linux_commands.json    # Base de données brute
├── requirements.txt           # Dépendances Python
└── README.md