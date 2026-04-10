"""
Agente generador de documentación.

Flujo:
  1. fetch_metadata  — consulta el toolbox para obtener schema y datos de muestra
  2. generate_draft  — usa Gemini para generar el JSON del documento
  3. save_draft      — guarda el borrador en Supabase con status='draft'
"""
import json
from datetime import datetime, timezone
from typing import TypedDict

import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from agents.prompts import build_generator_prompt, extract_text
from tools.mcp_client import (
    get_table_schema, get_sample_data,
    get_foreign_keys, get_indexes, get_row_count, get_ddl,
)
from tools.tableau_client import get_dashboard_metadata
from db.client import save_document, log_conversation, log_action
from config.object_types import type_config


# --- Estado del grafo ---

class GeneratorState(TypedDict):
    object_type: str       # 'table' | 'view' | 'dashboard' | 'stored_procedure'
    object_name: str       # nombre del objeto a documentar
    created_by: str        # usuario que lanza la generación
    metadata: dict         # schema y datos de muestra obtenidos del toolbox
    draft_content: dict    # JSON generado por Gemini
    document_id: str       # ID del documento guardado en Supabase
    error: str | None      # error si algo falla


# --- Nodos ---

async def fetch_metadata_node(state: GeneratorState) -> GeneratorState:
    """Consulta el toolbox para obtener schema, constraints, índices y datos de muestra."""
    object_name = state["object_name"]
    object_type = state["object_type"]

    cfg = type_config(object_type)
    fetch = cfg.get("metadata_fetch", [])
    metadata = {}

    if "schema" in fetch:
        metadata["schema"] = await get_table_schema(object_name)
        metadata["foreign_keys"] = await get_foreign_keys(object_name)
        metadata["indexes"] = await get_indexes(object_name)
        metadata["row_count"] = await get_row_count(object_name)
        metadata["ddl"] = await get_ddl(object_name)
    if "sample_data" in fetch:
        metadata["sample_data"] = await get_sample_data(object_name)
    if "tableau" in fetch:
        metadata["tableau"] = await get_dashboard_metadata(object_name)

    return {**state, "metadata": metadata}


async def generate_draft_node(state: GeneratorState) -> GeneratorState:
    """Usa Gemini para generar el JSON del documento a partir del metadata."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

    system_prompt = build_generator_prompt(state["object_type"], state["object_name"])

    meta = state["metadata"]
    parts = [f"Metadata disponible del objeto '{state['object_name']}':"]
    if meta.get("schema"):
        parts.append(f"\nSchema de columnas:\n{json.dumps(meta['schema'], indent=2)}")
    if meta.get("foreign_keys"):
        parts.append(f"\nForeign keys:\n{json.dumps(meta['foreign_keys'], indent=2)}")
    if meta.get("indexes"):
        parts.append(f"\nÍndices:\n{json.dumps(meta['indexes'], indent=2)}")
    if meta.get("row_count"):
        parts.append(f"\nConteo de filas: {meta['row_count']}")
    if meta.get("ddl"):
        parts.append(f"\nDDL (CREATE statement):\n{meta['ddl']}")
    if meta.get("sample_data"):
        parts.append(f"\nDatos de muestra:\n{json.dumps(meta['sample_data'], indent=2)}")
    if meta.get("tableau"):
        parts.append(f"\nMetadata de Tableau:\n{json.dumps(meta['tableau'], indent=2)}")
    parts.append("\nGenerá el documento JSON ahora.")
    user_message = "\n".join(parts)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    response = await llm.ainvoke(messages)
    raw_response = response.content

    # Limpiar el JSON si Gemini lo envuelve en bloques de código
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    # Intentar parsear, reintentar hasta 2 veces si falla
    draft_content = None
    last_error = None
    for attempt in range(3):
        try:
            draft_content = json.loads(cleaned)
            break
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt < 2:
                retry_msg = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                    HumanMessage(content="La respuesta anterior no era JSON válido. Respondé ÚNICAMENTE con el JSON, sin texto adicional ni bloques de código."),
                ]
                response = await llm.ainvoke(retry_msg)
                cleaned = extract_text(response)

    if draft_content is None:
        return {**state, "error": f"No se pudo parsear el JSON de Gemini: {last_error}"}

    # Registrar en conversation_log
    log_conversation(
        user_id=state["created_by"],
        agent_type="generator",
        prompt=user_message,
        response=raw_response,
    )

    return {**state, "draft_content": draft_content}


def _extract_field(content: dict, dotpath: str, default: str = "[REQUIERE REVISIÓN]") -> str:
    """Extrae un valor de un dict anidado usando dotpath (ej: 'identification.physical_name')."""
    keys = dotpath.split(".")
    current = content
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return default
    return current if current else default


async def save_draft_node(state: GeneratorState) -> GeneratorState:
    """Guarda el borrador en Supabase con status='draft'."""
    if state.get("error"):
        return state

    content = state["draft_content"]

    # Extraer campos del nuevo formato anidado, con fallback al formato plano
    name = (
        _extract_field(content, "identification.physical_name", "")
        or _extract_field(content, "identification.business_name", "")
        or content.get("name", state["object_name"])
    )
    business_domain = (
        _extract_field(content, "identification.business_domain", "")
        or content.get("business_domain", "[REQUIERE REVISIÓN]")
    )
    owner = (
        _extract_field(content, "governance.technical_owner", "")
        or content.get("owner", "[REQUIERE REVISIÓN]")
    )

    document = save_document({
        "name": name,
        "object_type": state["object_type"],
        "business_domain": business_domain,
        "status": "draft",
        "owner": owner,
        "content": content,
        "created_by": state["created_by"],
    })

    log_action(
        user_id=state["created_by"],
        action="generate",
        document_id=document["id"],
        metadata={"object_type": state["object_type"], "object_name": state["object_name"]},
    )

    return {**state, "document_id": document["id"]}


# --- Construcción del grafo ---

def build_generator_graph():
    graph = StateGraph(GeneratorState)

    graph.add_node("fetch_metadata", fetch_metadata_node)
    graph.add_node("generate_draft", generate_draft_node)
    graph.add_node("save_draft", save_draft_node)

    graph.set_entry_point("fetch_metadata")
    graph.add_edge("fetch_metadata", "generate_draft")
    graph.add_edge("generate_draft", "save_draft")
    graph.add_edge("save_draft", END)

    return graph.compile()


# --- Función principal ---

async def generate_document(object_type: str, object_name: str, created_by: str) -> dict:
    """
    Genera un borrador de documentación para el objeto indicado.

    Returns:
        dict con 'document_id' y 'content' si tuvo éxito,
        o 'error' si algo falló.
    """
    graph = build_generator_graph()

    initial_state: GeneratorState = {
        "object_type": object_type,
        "object_name": object_name,
        "created_by": created_by,
        "metadata": {},
        "draft_content": {},
        "document_id": "",
        "error": None,
    }

    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        return {"error": final_state["error"]}

    return {
        "document_id": final_state["document_id"],
        "content": final_state["draft_content"],
    }
