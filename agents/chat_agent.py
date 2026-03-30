"""
Agente de chat orquestador.

Usa LangGraph create_react_agent (ReAct) con tools que llaman a la API REST.
La memoria conversacional se maneja pasando el historial completo en cada llamada
— sin checkpointer, lo que mantiene el agente stateless y compatible con Streamlit.
"""
import requests
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from agents.prompts import CHAT_AGENT_SYSTEM_PROMPT
from config.object_types import OBJECT_TYPES

load_dotenv()

API = "http://localhost:8000"

# Usuario activo — se actualiza desde la UI antes de cada invocación
_current_user = "unknown"

def set_current_user(user: str):
    global _current_user
    _current_user = user


# Panel pendiente — las tools escriben acá; la UI lo lee después de invocar
_pending_panel: dict = {}

def get_pending_panel() -> dict:
    return _pending_panel.copy()

def clear_pending_panel():
    _pending_panel.clear()


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def listar_objetos_disponibles(object_type: str = "todos") -> str:
    """
    Lista los objetos disponibles en las fuentes de datos conectadas.
    Muestra nombre, tipo (tabla/vista), conexión y base de datos de cada objeto.

    Args:
        object_type: filtro de tipo — 'todos', 'table', 'view'
    """
    params = {}
    if object_type and object_type != "todos":
        params["object_type"] = object_type

    r = requests.get(f"{API}/toolbox/objects", params=params, timeout=15)
    if not r.ok:
        return f"No se pudo obtener la lista (error {r.status_code})."

    objects = r.json()
    if not objects:
        filtro = f" de tipo '{object_type}'" if object_type != "todos" else ""
        return f"No hay objetos{filtro} disponibles en las fuentes de datos."

    TYPE_LABELS = {"table": "Tabla", "view": "Vista"}

    rows = sorted(objects, key=lambda x: (x.get("connection",""), x.get("database_name",""), x.get("type",""), x.get("name","")))

    header = "| Nombre | Tipo | Conexión | Base de datos |\n|--------|------|----------|---------------|"
    table_rows = [
        f"| `{obj['name']}` | {TYPE_LABELS.get(obj.get('type',''), obj.get('type','?'))} | {obj.get('connection','?')} | {obj.get('database_name','?')} |"
        for obj in rows
    ]

    return f"Objetos disponibles ({len(objects)}):\n\n{header}\n" + "\n".join(table_rows)


@tool
def crear_documentacion(object_type: str, object_name: str) -> str:
    """
    Genera un borrador de documentación para un objeto de datos y lo abre en el panel.

    Args:
        object_type: tipo del objeto (table, view, dashboard, etl, stored_procedure)
        object_name: nombre exacto del objeto tal como aparece en la fuente de datos
    """
    r = requests.post(f"{API}/documents/generate", json={
        "object_type": object_type,
        "object_name": object_name,
        "created_by": _current_user,
    }, timeout=120)

    if r.status_code == 409:
        detail = r.json()["detail"]
        _pending_panel.update({"doc_id": detail["document_id"], "mode": "viewer"})
        return (
            f"Ya existe documentación para '{object_name}' "
            f"en estado '{detail['status']}'. La abrí en el panel."
        )

    if r.status_code == 422:
        detail = r.json().get("detail", {})
        suggestions = detail.get("suggestions", [])
        if suggestions:
            opts = ", ".join(suggestions)
            return (
                f"No encontré '{object_name}' exactamente. "
                f"Nombres similares encontrados: {opts}. "
                f"¿A cuál te referías?"
            )
        return f"No encontré ningún objeto llamado '{object_name}' en las fuentes de datos."

    if r.ok:
        doc_id = r.json()["document_id"]
        _pending_panel.update({"doc_id": doc_id, "mode": "editor"})
        return (
            f"Documentación generada para '{object_name}'. "
            f"La abrí en el panel — completá los campos faltantes antes de auditar."
        )

    return f"Error al generar: {r.text[:300]}"


@tool
def buscar_documentacion(pregunta: str) -> str:
    """
    Responde preguntas en lenguaje natural usando la documentación aprobada.
    Usá esta tool para preguntas sobre campos, tablas, ETLs, lógica de negocio, etc.

    Args:
        pregunta: la pregunta completa en lenguaje natural
    """
    r = requests.post(f"{API}/consultant/query", json={
        "question": pregunta,
        "user_id": _current_user,
    }, timeout=30)

    if r.ok:
        result = r.json()
        answer = result.get("answer", "Sin respuesta.")
        source = result.get("source", "")
        last_upd = result.get("last_updated", "")
        footer = f"\n\n*Fuente: {source} — última actualización: {last_upd}*" if source else ""

        # Si hay una fuente concreta, abrir ese documento en el panel
        if source:
            dr = requests.get(f"{API}/documents", params={"status": "approved"}, timeout=10)
            if dr.ok:
                matches = [d for d in dr.json() if d["name"].lower() == source.lower()]
                if matches:
                    _pending_panel.update({"doc_id": matches[0]["id"], "mode": "viewer"})

        return answer + footer

    return f"Error al consultar: {r.text[:200]}"


@tool
def listar_documentacion(status: str = "todos", object_type: str = "todos") -> str:
    """
    Lista los documentos de documentación existentes con filtros opcionales.
    Los borradores solo se muestran al admin o al creador.

    Args:
        status: estado del documento — todos, draft, approved, rejected
        object_type: tipo de objeto — todos, table, view, dashboard, etl, stored_procedure
    """
    params = {"user_id": _current_user, "role": "admin" if _current_user == "admin" else "developer"}
    if status != "todos":
        params["status"] = status
    if object_type != "todos":
        params["object_type"] = object_type

    r = requests.get(f"{API}/documents", params=params, timeout=10)
    if not r.ok:
        return f"Error al obtener documentos ({r.status_code})."

    docs = r.json()
    if not docs:
        return "No hay documentos con esos filtros."

    lines = [f"  • **{d['name']}** ({d['object_type']}) — `{d['status']}`" for d in docs]
    return f"Documentos ({len(docs)}):\n" + "\n".join(lines)


@tool
def abrir_documento(document_name: str) -> str:
    """
    Busca un documento por nombre y lo abre en el panel lateral para visualizarlo o editarlo.
    Usá esta tool cuando el usuario quiera ver, revisar o editar un documento existente.

    Args:
        document_name: nombre del objeto documentado (ej: 'Orders', 'fact_sales')
    """
    r = requests.get(f"{API}/documents", params={
        "user_id": _current_user,
        "role": "admin",  # el agente ve todos los docs para poder abrirlos
    }, timeout=10)
    if not r.ok:
        return "No se pudo acceder a los documentos."

    docs = [d for d in r.json() if d["name"].lower() == document_name.lower()]
    if not docs:
        return f"No encontré ningún documento llamado '{document_name}'."

    doc = docs[0]
    mode = "editor" if doc["status"] == "draft" else "viewer"
    _pending_panel.update({"doc_id": doc["id"], "mode": mode})
    return (
        f"Abrí '{doc['name']}' en el panel "
        f"({'modo edición' if mode == 'editor' else 'modo visor'}, estado: {doc['status']})."
    )


@tool
def auditar_documento(document_name: str) -> str:
    """
    Envía a auditoría automática un documento en estado draft.

    Args:
        document_name: nombre del objeto documentado (ej: 'Orders', 'fact_sales')
    """
    r = requests.get(f"{API}/documents", params={"status": "draft"}, timeout=10)
    if not r.ok:
        return "No se pudo acceder a los documentos."

    docs = [d for d in r.json() if d["name"].lower() == document_name.lower()]
    if not docs:
        return (
            f"No encontré un borrador para '{document_name}'. "
            f"¿Ya fue aprobado, o el nombre es distinto?"
        )

    doc = docs[0]
    ar = requests.post(
        f"{API}/documents/{doc['id']}/audit",
        json={"audited_by": _current_user},
        timeout=60,
    )

    if not ar.ok:
        return f"Error al auditar: {ar.text[:200]}"

    result = ar.json()
    res = result.get("result")
    _pending_panel.update({"doc_id": doc["id"], "mode": "viewer"})

    if res == "approved":
        return f"'{document_name}' fue **aprobado** ✅ y ya está disponible para consultas."
    elif res == "observations":
        issues = "\n".join(
            f"  - **{i['field']}**: {i['issue']}" for i in result.get("issues", [])
        )
        return f"'{document_name}' tiene observaciones 🟡:\n{issues}"
    else:
        issues = "\n".join(
            f"  - **{i['field']}**: {i['issue']}" for i in result.get("issues", [])
        )
        return f"'{document_name}' fue rechazado ❌:\n{issues}"


# ── Construcción del agente ──────────────────────────────────────────────────

TOOLS = [
    listar_objetos_disponibles,
    crear_documentacion,
    buscar_documentacion,
    listar_documentacion,
    auditar_documento,
    abrir_documento,
]

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        valid_types = ", ".join(OBJECT_TYPES.keys())
        system_prompt = CHAT_AGENT_SYSTEM_PROMPT.format(valid_types=valid_types)
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
        _agent = create_react_agent(llm, TOOLS, prompt=system_prompt)
    return _agent


# ── Función principal ────────────────────────────────────────────────────────

async def stream_chat(message: str, history: list[dict] | None = None):
    """
    Versión async/streaming de invoke_chat.
    Yields strings de texto a medida que el LLM los genera.
    """
    agent = _get_agent()

    messages = []
    for msg in (history or []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    try:
        async for event in agent.astream_events({"messages": messages}, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                yield text
                elif isinstance(content, str) and content:
                    yield content
    except Exception as e:
        yield f"Error interno del agente: {e}"


def invoke_chat(message: str, history: list[dict] | None = None) -> str:
    """
    Invoca el agente con el mensaje actual y el historial de la conversación.

    Args:
        message:  mensaje del usuario (turno actual)
        history:  lista de {"role": "user"|"assistant", "content": "..."}
                  con los turnos anteriores de la sesión
    Returns:
        Respuesta en texto del agente
    """
    agent = _get_agent()

    # Reconstruir historial como mensajes de LangChain
    messages = []
    for msg in (history or []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    try:
        response = agent.invoke({"messages": messages})
        content = response["messages"][-1].content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        return content
    except Exception as e:
        return f"Error interno del agente: {e}"
