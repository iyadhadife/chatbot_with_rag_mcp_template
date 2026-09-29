from history_manager import HistoryManager
from system_prompt import get_system_instructions

def handle_context_command(tool_map):
    """Gère le raccourci /context en appelant directement l'outil MCP d'ingestion."""
    print("\n[SYSTÈME] Appel de l'outil 'ingest_documents' sur le serveur MCP... 🔄")
    try:
        ingest_tool = tool_map.get("ingest_documents")
        if ingest_tool:
            result = ingest_tool.invoke({})
            print(f"[SYSTÈME] ✅ Résultat : {result}")
        else:
            print("[SYSTÈME] ❌ Erreur : L'outil 'ingest_documents' est introuvable.")
    except Exception as e:
        print(f"[SYSTÈME] ❌ Erreur lors de l'appel MCP : {e}")

def process_user_turn(user_query: str, llm_with_tools, tool_map, history_manager: HistoryManager):
    """Traite l'interaction avec le LLM, l'exécution des outils et le streaming."""
    history_manager.add_user_message(user_query)
    
    response = llm_with_tools.invoke(history_manager.get_history())
    history_manager.get_history().append(response)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            print(f"\n[Exécution de l'outil '{tool_name}' via MCP...]")
            selected_tool = tool_map.get(tool_name)
            tool_result = selected_tool.invoke(tool_args) if selected_tool else "Erreur : Outil inconnu."
                
            history_manager.add_tool_message(str(tool_result), tool_id)
        
        print("\nAssistant : ", end="", flush=True)
        full_response = ""
        for chunk in llm_with_tools.stream(history_manager.get_history()):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                full_response += chunk.content
                
        history_manager.add_ai_message(full_response)
    else:
        print(f"\nAssistant : {response.content}")