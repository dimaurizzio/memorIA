"""
Agente auditor de documentación.

Flujo:
  1. load_document   — carga el documento draft desde Supabase
  2. evaluate        — usa Gemini para evaluar calidad y completitud
  3. update_status   — actualiza el status en Supabase y registra en audit_log
  4. trigger_indexing — solo si approved, dispara el worker de indexación
"""
import json
from typing import TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from agents.prompts import build_auditor_prompt, extract_text
from db.client import (
    get_document,
    update_document,
    save_audit_issues,
    log_audit,
    log_conversation,
    log_action,
)


# --- Estado del grafo ---

class AuditorState(TypedDict):
    document_id: str       # ID del documento a auditar
    audited_by: str        # usuario que lanza la auditoría
    document: dict         # documento cargado desde Supabase
    result: str            # 'approved' | 'observations'
    issues: list[dict]     # lista de problemas encontrados
    error: str | None


# --- Nodos ---

async def load_document_node(state: AuditorState) -> AuditorState:
    """Carga el documento desde Supabase y verifica que esté en estado draft."""
    document = get_document(state["document_id"])

    if not document:
        return {**state, "error": f"Documento {state['document_id']} no encontrado."}

    if document["status"] != "draft":
        return {**state, "error": f"El documento debe estar en estado 'draft' para auditarse. Estado actual: {document['status']}"}

    return {**state, "document": document}


async def evaluate_node(state: AuditorState) -> AuditorState:
    """Usa Gemini para evaluar la calidad del documento."""
    if state.get("error"):
        return state

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

    system_prompt = build_auditor_prompt(
        object_type=state["document"]["object_type"],
        document_json=json.dumps(state["document"]["content"], indent=2, ensure_ascii=False),
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="Evaluá el documento y respondé con el JSON de resultado."),
    ]

    response = await llm.ainvoke(messages)
    raw_response = response.content

    # Limpiar bloques de código si Gemini los agrega
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    # Parsear respuesta con reintento
    evaluation = None
    last_error = None
    for attempt in range(3):
        try:
            evaluation = json.loads(cleaned)
            break
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt < 2:
                retry_msg = messages + [
                    HumanMessage(content="Respondé ÚNICAMENTE con el JSON, sin texto adicional ni bloques de código."),
                ]
                response = await llm.ainvoke(retry_msg)
                cleaned = extract_text(response)

    if evaluation is None:
        return {**state, "error": f"No se pudo parsear la evaluación de Gemini: {last_error}"}

    # Registrar en conversation_log
    log_conversation(
        user_id=state["audited_by"],
        agent_type="auditor",
        prompt=f"Auditoría del documento {state['document_id']}",
        response=raw_response,
        document_id=state["document_id"],
    )

    return {
        **state,
        "result": evaluation["result"],
        "issues": evaluation.get("issues", []),
    }


async def update_status_node(state: AuditorState) -> AuditorState:
    """Actualiza el status del documento y registra en audit_log."""
    if state.get("error"):
        return state

    result = state["result"]
    document_id = state["document_id"]
    previous_status = state["document"]["status"]

    # Siempre draft hasta que sea aprobado — no existe estado "rechazado"
    new_status = "approved" if result == "approved" else "draft"

    # Persistir issues en el documento para que el editor los muestre
    save_audit_issues(document_id, state["issues"] if result != "approved" else [])

    # Armar notas para el audit_log
    notes = None
    if state["issues"]:
        notes = json.dumps(state["issues"], ensure_ascii=False)

    # Actualizar documento
    update_data = {"status": new_status}
    if result == "approved":
        from datetime import datetime, timezone
        update_data["approved_by"] = state["audited_by"]
        update_data["approved_at"] = datetime.now(timezone.utc).isoformat()

    update_document(document_id, update_data)

    # Registrar en audit_log
    log_audit(
        document_id=document_id,
        user_id=state["audited_by"],
        previous_status=previous_status,
        new_status=new_status,
        approval_type="automatic",
        notes=notes,
    )

    # Registrar acción
    log_action(
        user_id=state["audited_by"],
        action="audit",
        document_id=document_id,
        metadata={"result": result, "issues_count": len(state["issues"])},
    )

    return state


async def trigger_indexing_node(state: AuditorState) -> AuditorState:
    """Dispara el worker de indexación para documentos aprobados."""
    # El worker escucha webhooks de Supabase, pero también podemos llamarlo directamente
    # En producción esto lo maneja el webhook automáticamente
    # Aquí lo llamamos explícitamente para el flujo síncrono
    try:
        from workers.indexer import index_document
        await index_document(state["document_id"])
    except Exception as e:
        # No es crítico si falla — el job de reconciliación lo va a indexar igual
        print(f"Warning: indexación falló para {state['document_id']}: {e}")

    return state


# --- Construcción del grafo ---

def build_auditor_graph():
    graph = StateGraph(AuditorState)

    graph.add_node("load_document", load_document_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("update_status", update_status_node)
    graph.add_node("trigger_indexing", trigger_indexing_node)

    graph.set_entry_point("load_document")
    graph.add_edge("load_document", "evaluate")
    graph.add_edge("evaluate", "update_status")

    # Solo indexar si fue aprobado
    graph.add_conditional_edges(
        "update_status",
        lambda state: "index" if state.get("result") == "approved" and not state.get("error") else "end",
        {
            "index": "trigger_indexing",
            "end": END,
        }
    )
    graph.add_edge("trigger_indexing", END)

    return graph.compile()


# --- Función principal ---

async def audit_document(document_id: str, audited_by: str) -> dict:
    """
    Audita un documento en estado draft.

    Returns:
        dict con 'result' ('approved'|'observations'|'rejected') e 'issues'.
    """
    graph = build_auditor_graph()

    initial_state: AuditorState = {
        "document_id": document_id,
        "audited_by": audited_by,
        "document": {},
        "result": "",
        "issues": [],
        "error": None,
    }

    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        return {"error": final_state["error"]}

    return {
        "result": final_state["result"],
        "issues": final_state["issues"],
    }
