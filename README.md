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
