import asyncio
import base64
import json
import logging
import os
import traceback

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from config import get_llms, list_ollama_models, DEFAULT_MODEL
from system_prompt import get_system_instructions
from history_manager import HistoryManager
from langchain_core.messages import ToolMessage

from mcp import ClientSession
from mcp.client.sse import sse_client

app = Flask(__name__)
CORS(app)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── Global initialisation ─────────────────────────────────────────────────────
history_manager = HistoryManager(get_system_instructions())

MCP_URL     = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001/sse")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT_SECONDS", "120"))  # long calls (RAG + LLM)


# ── MCP helper ────────────────────────────────────────────────────────────────
async def _call_mcp_once(tool_name: str, arguments: dict) -> str:
    async with sse_client(MCP_URL) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if hasattr(result, "content") and result.content:
                return "\n".join(getattr(c, "text", str(c)) for c in result.content)
            return str(result)


async def _call_mcp(tool_name: str, arguments: dict = None, retries: int = 1) -> str:
    """
    Appelle un outil MCP avec timeout et retry.
    - MCPError / ConnectionClosed → retry une fois avant d'échouer
    - asyncio.TimeoutError → propagé directement (pas la peine de retenter)
    """
    args = arguments or {}
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(
                _call_mcp_once(tool_name, args),
                timeout=MCP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"L'outil MCP '{tool_name}' n'a pas répondu dans {MCP_TIMEOUT:.0f}s."
            )
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    f"MCP '{tool_name}' — tentative {attempt + 1} échouée ({exc}), retry…"
                )
                await asyncio.sleep(1)
    raise last_exc  # type: ignore[misc]


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── API routes ────────────────────────────────────────────────────────────────
@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json() or {}
    user_query = data.get("message", "").strip()
    model_name = (data.get("model") or DEFAULT_MODEL).strip()
    if not user_query:
        return jsonify({"error": "Message vide"}), 400

    # Modèle choisi par l'utilisateur (sinon modèle par défaut)
    llm_with_tools, llm_base = get_llms(model_name)

    def generate():
        try:
            # Messages du tour : l'historique n'est inclus que si la question
            # en dépend, et les passages RAG ne survivent pas au tour.
            messages = history_manager.build_messages(user_query)

            # Phase 1 – sélection d'outil (non-streaming)
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else tc.name
                    args = tc.get("args", {}) if isinstance(tc, dict) else tc.args
                    tid  = tc.get("id", "call_0") if isinstance(tc, dict) else getattr(tc, "id", "call_0")

                    # Notify frontend which tool is running
                    yield f"data: {json.dumps({'status': name})}\n\n"

                    # Le petit LLM reformule mal (« appartien au », noms inventés) :
                    # on cherche avec la question réelle de l'utilisateur.
                    if name == "search_documents":
                        args = {**args, "query": history_manager.search_query(user_query)}

                    try:
                        result = run_async(_call_mcp(name, args))
                    except Exception as e:
                        result = f"Erreur outil: {e}"

                    # Stream the tool result so the frontend can show sources
                    if name == "search_documents":
                        yield f"data: {json.dumps({'context': result, 'search_query': args.get('query', '')})}\n\n"

                    messages.append(ToolMessage(content=str(result), tool_call_id=tid))

                # Phase 2 – stream final answer
                full = ""
                for chunk in llm_base.stream(messages):
                    if chunk.content:
                        full += chunk.content
                        yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
                history_manager.add_exchange(user_query, full)

            else:
                # Direct answer – send in one shot
                history_manager.add_exchange(user_query, response.content)
                yield f"data: {json.dumps({'chunk': response.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/reset", methods=["POST"])
def reset_endpoint():
    """Nouvelle conversation : oublie l'historique côté serveur."""
    history_manager.reset()
    return jsonify({"status": "success"})


@app.route("/api/models", methods=["GET"])
def models_endpoint():
    """Liste les modèles Ollama installés localement (pour le sélecteur)."""
    try:
        models = list_ollama_models()
        default = DEFAULT_MODEL if DEFAULT_MODEL in models else (models[0] if models else DEFAULT_MODEL)
        return jsonify({"models": models, "default": default})
    except Exception as e:
        logger.error(f"Erreur liste modèles Ollama : {e}")
        return jsonify({
            "models": [DEFAULT_MODEL],
            "default": DEFAULT_MODEL,
            "error": "Ollama injoignable — modèle par défaut utilisé.",
            "detail": str(e),
        }), 502


@app.route("/api/chunks", methods=["GET"])
def chunks_endpoint():
    """Inventaire des chunks indexés (pour l'onglet d'inspection)."""
    try:
        raw = run_async(_call_mcp("list_indexed_chunks", {}))
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = {"total": 0, "documents": [], "error": "Réponse MCP non-JSON", "raw": str(raw)[:500]}
        return jsonify(data)
    except TimeoutError as e:
        logger.error(f"Timeout list_indexed_chunks : {e}")
        return jsonify({"total": 0, "documents": [], "error": str(e)}), 504
    except Exception as e:
        logger.error(f"Erreur connexion MCP (list_indexed_chunks) : {e}")
        return jsonify({
            "total": 0, "documents": [],
            "error": "Le serveur MCP est injoignable ou a planté.",
            "detail": str(e),
        }), 502


@app.route("/api/context", methods=["POST"])
def context_endpoint():
    try:
        result = run_async(_call_mcp("ingest_documents", {}))
        return jsonify({"status": "success", "message": str(result)})
    except TimeoutError as e:
        logger.error(f"Timeout ingestion MCP : {e}")
        return jsonify({"status": "error", "message": str(e)}), 504
    except Exception as e:
        logger.error(f"Erreur connexion MCP (ingest_documents) : {e}")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": "Le serveur MCP est injoignable ou a planté. Vérifiez les logs du conteneur mcp-server.",
            "detail": str(e),
        }), 502


@app.route("/api/upload", methods=["POST"])
def upload_endpoint():
    """Ajoute et indexe un ou plusieurs PDF sans toucher à la base existante."""
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        return jsonify({"status": "error", "message": "Aucun fichier reçu."}), 400
    results, ok = [], True
    for f in files:
        try:
            payload = base64.b64encode(f.read()).decode("ascii")
            msg = str(run_async(_call_mcp(
                "add_document", {"filename": f.filename, "content_base64": payload}
            )))
            ok = ok and msg.endswith("indexé.")
            results.append(msg)
        except Exception as e:
            logger.error(f"Erreur ajout {f.filename} : {e}")
            ok = False
            results.append(f"{f.filename} : erreur ({e})")
    return jsonify({"status": "success" if ok else "error", "message": "\n".join(results)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
