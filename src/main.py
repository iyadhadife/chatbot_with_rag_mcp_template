import asyncio
from pathlib import Path
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain_ollama import ChatOllama

# Import de ta fonction personnalisée
from chat_engine.generate_answer import generer_reponse_expert

# --- CONFIGURATION ---
URL_MCP = "http://localhost:8000/sse"
MODEL_NAME = "qwen2.5:0.5b"
INSTRUCTIONS_FILE = "linux_expert.md"

async def main():
    # 1. Chargement des instructions
    try:
        instructions = Path(INSTRUCTIONS_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        instructions = "Tu es un expert Linux."

    # 2. Initialisation du modèle local
    llm = ChatOllama(model=MODEL_NAME, temperature=0)

    print(f"Tentative de connexion au serveur MCP...")
    
    try:
        async with sse_client(URL_MCP) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("Connecté au RAG. Tapez 'exit' pour quitter.")
                
                while True:
                    user_input = input("\nQuestion > ")
                    if user_input.lower() in ["exit", "quit"]:
                        break
                    
                    if not user_input.strip():
                        continue

                    # On appelle la logique située dans chat_engine
                    await generer_reponse_expert(session, llm, instructions, user_input)

    except Exception as e:
        print(f"Erreur de connexion au serveur MCP : {e}")
        print("Vérifie que ton serveur MCP est bien lancé sur http://localhost:8000")

if __name__ == "__main__":
    asyncio.run(main())