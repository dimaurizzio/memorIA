"""
Endpoint de chat — wraps el agente orquestador ReAct con streaming SSE.
"""
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents.chat_agent import stream_chat, set_current_user, get_pending_panel, clear_pending_panel

router = APIRouter(tags=["chat"])

_KEEPALIVE_INTERVAL = 10   # segundos entre pings SSE
_AGENT_TIMEOUT     = 300   # segundos máximos de espera total


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    user: str = "anonymous"


@router.post("/chat")
async def chat_stream(body: ChatRequest):
    """
    Invoca el agente de chat con streaming SSE.
    Emite: {"type":"text","content":"..."} por cada token
    Finaliza con: {"type":"done","pending_panel":...}

    El agente corre en una tarea independiente (create_task) para que no se
    cancele si el proxy de Next.js o el browser cierran la conexión antes de
    que Gemini/Tableau respondan. Se envían keepalives SSE cada 10 segundos
    para mantener la conexión viva durante operaciones lentas.
    """
    clear_pending_panel()
    set_current_user(body.user)

    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def run_agent():
        try:
            async for token in stream_chat(body.message, body.history):
                await queue.put({"type": "text", "content": token})
        except Exception as e:
            await queue.put({"type": "text", "content": f"Error interno: {e}"})
        finally:
            panel = get_pending_panel() or None
            await queue.put({"type": "done", "pending_panel": panel})

    # Tarea independiente del scope ASGI — no se cancela si cae la conexión HTTP
    asyncio.create_task(run_agent())

    async def generate():
        elapsed = 0
        while elapsed < _AGENT_TIMEOUT:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
            except asyncio.TimeoutError:
                # Keepalive: comentario SSE ignorado por el browser pero mantiene
                # la conexión viva a través del proxy de Next.js
                yield ": keepalive\n\n"
                elapsed += _KEEPALIVE_INTERVAL
                continue

            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] == "done":
                break
        else:
            yield f"data: {json.dumps({'type': 'done', 'pending_panel': None})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
