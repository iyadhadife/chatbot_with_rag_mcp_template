# Local RAG Chatbot with Ollama & ChromaDB

A containerized Retrieval-Augmented Generation (RAG) pipeline designed to interact locally with professional documents (such as CVs and commercial quotes/devis) using LangChain, ChromaDB, and local LLMs powered by Ollama.

---

## 🚀 Features

* **100% Local Execution:** Runs completely offline using Ollama (supporting models like `qwen2.5:7b`).
* **Automatic Document Classification:** Uses the LLM during ingestion to automatically categorize PDF documents (e.g., `CV`, `DEVIS`) and store them with enriched metadata (`source` and `doc_type`).
* **Vector Storage:** Utilizes ChromaDB via HTTP client for efficient and persistent document chunk retrieval.
* **Streaming Responses:** Real-time token generation for a smooth, conversational user experience.
* **Containerized Environment:** Fully orchestrated using Docker and Docker Compose.
* **MCP Integration:** Model Context Protocol (MCP) servers will soon be introduced to orchestrate multi-source document queries and tool execution cleanly.

---

## 📁 Project Structure

```text
chatbot_with_rag_mcp_template/
│
├── data/
│   └── pdfs/              # Place your source PDFs here (CVs, quotes, etc.)
├── src/
│   └── chatbot_langchain/
│       ├── main.py        # Main conversational loop with streaming and history
│       └── rag_pipeline/
│           ├── ingest.py  # PDF text extraction, AI classification, and ChromaDB storage
│           └── retriever.py # Context formatting with explicit metadata headers
├── Dockerfile             # Container configuration for the chatbot app
├── docker-compose.yml     # Multi-container setup (ChromaDB & Chatbot)
└── requirements.txt       # Python dependencies


docker-compose up