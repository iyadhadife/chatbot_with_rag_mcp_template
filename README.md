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


docker compose up --build -d
docker compose run --rm chatbot python src/chatbot_langchain/rag_pipeline/ingest.py
docker compose run --rm chatbot python src/chatbot_langchain/main.py/
# 🤖 Chatbot with RAG & MCP Template

A structured Python project template for building an intelligent assistant combining Retrieval-Augmented Generation (RAG) and the Model Context Protocol (MCP). Ideal for Agent-to-Agent architectures or information system integrations.

## 🚀 Key Features

- **RAG Engine (Retrieval-Augmented Generation):** Document data ingestion and advanced semantic search to ground the model's responses in concrete facts.
- **MCP Server (Model Context Protocol):** Seamless integration with external tools and context management via a standardized architecture, facilitating multi-agent workflows.
- **Chat Engine:** Python orchestration of accurate and contextualized response generation relying on retrieved data.
- **Expert Personas:** Support for specific personas via textual instructions (e.g., `linux_expert.md`).
- **Flexible Data Sources:** Native processing of files (like `linux_commands.json`) to enrich the knowledge base.

## 📁 Project Architecture

```text
chatbot_with_rag_mcp_template/
├── data/
│   └── linux_commands.json       # Source database for RAG
├── src/
│   ├── chat_engine/
│   │   └── generate_answer.py    # LLM response generation logic
│   ├── mcp_server/
│   │   ├── server.py             # MCP server configuration and initialization
│   │   └── tools.py              # Definition of tools accessible via MCP
│   ├── rag_engine/
│   │   ├── ingest.py             # Ingestion and indexing (vectorization) script
│   │   └── retriever.py          # Semantic search logic
│   ├── linux_expert.md           # System prompt / Persona context
│   ├── main.py                   # Main entry point of the application
│   └── rag_test.py               # Unit test script for the RAG pipeline
├── .gitignore
├── README.md
└── requirements.txt              # Project dependencies
