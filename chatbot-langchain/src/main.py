import asyncio
import json
import os
import traceback

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from config import init_llm_with_tools
from system_prompt import get_system_instructions
from history_manager import HistoryManager
from langchain_core.messages import ToolMessage, AIMessage

from mcp import ClientSession
from mcp.client.sse import sse_client

app = Flask(__name__)
CORS(app)

# ── Global initialisation ─────────────────────────────────────────────────────
llm_with_tools, llm_base, tools = init_llm_with_tools()
history_manager = HistoryManager(get_system_instructions())

MCP_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001/sse")


# ── MCP helper ────────────────────────────────────────────────────────────────
async def _call_mcp(tool_name: str, arguments: dict = None):
    async with sse_client(MCP_URL) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            if hasattr(result, "content") and result.content:
                return "\n".join(getattr(c, "text", str(c)) for c in result.content)
            return str(result)


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
    if not user_query:
        return jsonify({"error": "Message vide"}), 400

    def generate():
        try:
            history_manager.add_user_message(user_query)

            # Phase 1 – tool selection (non-streaming, fast with 0.5b)
            response = llm_with_tools.invoke(history_manager.get_history())
            history_manager.get_history().append(response)

            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else tc.name
                    args = tc.get("args", {}) if isinstance(tc, dict) else tc.args
                    tid  = tc.get("id", "call_0") if isinstance(tc, dict) else getattr(tc, "id", "call_0")

                    # Notify frontend which tool is running
                    yield f"data: {json.dumps({'status': name})}\n\n"

                    try:
                        result = run_async(_call_mcp(name, args))
                    except Exception as e:
                        result = f"Erreur outil: {e}"

                    history_manager.add_tool_message(str(result), tid)

                # Phase 2 – stream final answer
                full = ""
                for chunk in llm_base.stream(history_manager.get_history()):
                    if chunk.content:
                        full += chunk.content
                        yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
                history_manager.add_ai_message(full)

            else:
                # Direct answer – send in one shot
                history_manager.add_ai_message(response.content)
                yield f"data: {json.dumps({'chunk': response.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            traceback.print_exc()
            history_manager.rollback_last()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/context", methods=["POST"])
def context_endpoint():
    try:
        result = run_async(_call_mcp("ingest_documents", {}))
        return jsonify({"status": "success", "message": str(result)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
