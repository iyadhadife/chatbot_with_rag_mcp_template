import sys
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

async def generer_reponse_expert(session, llm, instructions, question):
    """
    Interroge le RAG via MCP et stream la réponse de l'LLM.
    """
    # 1. Récupération des données du RAG (MCP)
    try:
        result_rag = await session.call_tool(
            "interroger_base_connaissance", 
            arguments={"question": question}
        )
        contexte_rag = result_rag.content[0].text
    except Exception as e:
        contexte_rag = f"(Note : Impossible de joindre le RAG : {e})"

    # 2. Préparation des messages
    messages = [
        SystemMessage(content=f"{instructions}\n\nCONTEXTE RAG :\n{contexte_rag}"),
        HumanMessage(content=question)
    ]

    # 3. Streaming de la réponse
    print("\n[EXPERT LINUX] > ", end="", flush=True)
    
    async for chunk in llm.astream(messages):
        print(chunk.content, end="", flush=True)
    
    print("\n" + "-" * 30)