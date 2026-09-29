import asyncio
import traceback
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from config import init_llm_with_tools
from system_prompt import get_system_instructions
from history_manager import HistoryManager

# Import LangChain message pour le retour du tool
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage

# Client MCP SSE
from mcp import ClientSession
from mcp.client.sse import sse_client

app = Flask(__name__)
CORS(app)

# Initialisation
llm_with_tools, tools = init_llm_with_tools()
tool_map = {tool.name: tool for tool in tools}
history_manager = HistoryManager(get_system_instructions())

async def call_mcp_tool_async(tool_name: str, arguments: dict = None):
    """Appel sécurisé du tool sur le serveur MCP via SSE."""
    if arguments is None:
        arguments = {}
    
    mcp_url = "http://mcp-server:8001/sse"
    
    async with sse_client(mcp_url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            
            # Extraction sécurisée du contenu renvoyé par FastMCP
            if hasattr(result, "content") and result.content:
                texts = [getattr(c, "text", str(c)) for c in result.content]
                return "\n".join(texts)
            return str(result)

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data = request.json or {}
    user_query = data.get("message", "").strip()
    
    if not user_query:
        return jsonify({"error": "Message vide."}), 400

    try:
        # Ajout du message utilisateur
        if hasattr(history_manager, "add_user_message"):
            history_manager.add_user_message(user_query)
        else:
            history_manager.get_history().append(HumanMessage(content=user_query))
        
        # Premier appel LLM
        response = llm_with_tools.invoke(history_manager.get_history())
        history_manager.get_history().append(response)
        
        # Si le modèle réclame un ou plusieurs outils
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name") if isinstance(tool_call, dict) else tool_call.get("name")
                tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else tool_call.get("args", {})
                
                # Récupération sécurisée de l'ID du tool_call (dictionnaire ou objet)
                if isinstance(tool_call, dict):
                    tool_id = tool_call.get("id", "call_default")
                else:
                    tool_id = getattr(tool_call, "id", "call_default")
                
                print(f"\n[Flask] Exécution outil MCP '{tool_name}' (ID: {tool_id}) avec {tool_args}...")
                tool_output = run_async(call_mcp_tool_async(tool_name, tool_args))
                print(f"[Flask] Réponse reçue du MCP : {str(tool_output)[:100]}...")

                # Ajout du retour d'outil dans l'historique de manière sécurisée
                try:
                    history_manager.add_tool_message(str(tool_output), tool_id)
                except Exception:
                    history_manager.get_history().append(
                        ToolMessage(content=str(tool_output), tool_call_id=tool_id)
                    )
            
            # Deuxième appel LLM avec le contexte du tool
            final_response = llm_with_tools.invoke(history_manager.get_history())
            reply_text = final_response.content
            
            if hasattr(history_manager, "add_ai_message"):
                history_manager.add_ai_message(reply_text)
            else:
                history_manager.get_history().append(AIMessage(content=reply_text))
        else:
            reply_text = response.content
            if hasattr(history_manager, "add_ai_message"):
                history_manager.add_ai_message(reply_text)
            
        return jsonify({"response": reply_text})
        
    except Exception as e:
        # Affiche la trace d'erreur exacte dans le terminal docker
        print(f"\n[ERREUR FLASK CHAT] : {e}")
        traceback.print_exc()
        
        if hasattr(history_manager, "rollback_last"):
            history_manager.rollback_last()
            
        return jsonify({"error": str(e)}), 500

@app.route("/api/context", methods=["POST"])
def context_endpoint():
    try:
        print("\n[Flask] Déclenchement de l'ingestion via le serveur MCP...")
        result = run_async(call_mcp_tool_async("ingest_documents", {}))
        return jsonify({"status": "success", "message": str(result)})
    except Exception as e:
        print(f"\n[ERREUR FLASK CONTEXT] : {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)