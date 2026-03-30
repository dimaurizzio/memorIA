"""
Agente consultor RAG (Retrieval-Augmented Generation).

Flujo:
  1. embed_question    — convierte la pregunta en un vector de búsqueda
  2. search_documents  — busca los documentos más relevantes en pgvector
  3. generate_answer   — usa Gemini para responder basándose en los documentos encontrados
  4. log_conversation  — registra la interacción en conversation_log
"""
import json
import re
from typing import TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from agents.prompts import CONSULTANT_SYSTEM_PROMPT
from tools.embedding import generate_query_embedding, document_to_full_context
from db.client import search_documents, log_conversation, get_document


# --- Estado del grafo ---

class ConsultantState(TypedDict):
    question: str          # pregunta del usuario
    user_id: str           # usuario que consulta
    query_embedding: list  # vector de la pregunta
    results: list[dict]    # documentos relevantes encontrados
    context: str           # contexto formateado para el prompt
    answer: str            # respuesta generada
    source: str            # fuente citada
    last_updated: str      # fecha del documento más reciente
    error: str | None


# --- Nodos ---

async def embed_question_node(state: ConsultantState) -> ConsultantState:
    """Convierte la pregunta en un vector de búsqueda."""
    embedding = generate_query_embedding(state["question"])
    return {**state, "query_embedding": embedding}


async def search_documents_node(state: ConsultantState) -> ConsultantState:
    """Busca documentos relevantes en pgvector."""
    results = search_documents(
        query_embedding=state["query_embedding"],
        match_count=5,
        similarity_threshold=0.5,  # umbral más bajo para mayor recall
    )

    if not results:
        return {**state, "results": [], "context": ""}

    # Enriquecer resultados con el contenido completo del documento
    enriched = []
    for row in results:
        doc = get_document(row["document_id"])
        if doc:
            enriched.append({
                "document_id": row["document_id"],
                "similarity": row["similarity"],
                "full_context": document_to_full_context(doc),
                "name": doc["name"],
                "last_updated": doc.get("updated_at", ""),
            })

    # Formatear el contexto para el prompt
    context_parts = []
    for r in enriched:
        context_parts.append(
            f"--- Documento: {r['name']} (similitud: {r['similarity']:.2f}) ---\n{r['full_context']}"
        )
    context = "\n\n".join(context_parts)

    return {**state, "results": enriched, "context": context}


async def generate_answer_node(state: ConsultantState) -> ConsultantState:
    """Genera la respuesta usando Gemini con el contexto recuperado."""
    if not state["context"]:
        return {
            **state,
            "answer": "No encontré documentación aprobada sobre esto.",
            "source": "",
            "last_updated": "",
        }

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

    prompt = CONSULTANT_SYSTEM_PROMPT.format(
        context=state["context"],
        question=state["question"],
    )

    messages = [HumanMessage(content=prompt)]
    response = await llm.ainvoke(messages)
    raw = response.content.strip()

    # Parsear JSON estructurado con reintento (igual que generator y auditor)
    parsed = None
    last_error = None
    current_messages = messages + [response]
    for attempt in range(3):
        try:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            parsed = json.loads(cleaned.strip())
            break
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt < 2:
                retry_msg = current_messages + [
                    HumanMessage(content="Respondé ÚNICAMENTE con el JSON, sin texto adicional ni bloques de código."),
                ]
                retry_response = await llm.ainvoke(retry_msg)
                raw = retry_response.content.strip()
                current_messages = retry_msg + [retry_response]

    if parsed is None:
        # Fallback: devolver el texto crudo si no se pudo parsear
        return {
            **state,
            "answer": raw,
            "source": state["results"][0].get("name", "") if state["results"] else "",
            "last_updated": state["results"][0].get("last_updated", "") if state["results"] else "",
        }

    answer = parsed.get("answer", "")
    cited_name = parsed.get("source")  # nombre exacto que el LLM declaró haber usado

    # Buscar el documento citado en los resultados recuperados
    source = ""
    last_updated = ""
    if cited_name:
        matched = next(
            (r for r in state["results"] if r["name"].lower() == cited_name.lower()),
            None,
        )
        if matched:
            source = matched["name"]
            last_updated = matched.get("last_updated", "")
        else:
            # El LLM citó un nombre que no está en los resultados — usar el nombre tal cual
            source = cited_name

    # Fallback: si el LLM devolvió source null, usar el resultado de mayor similitud
    if not source and state["results"]:
        source = state["results"][0].get("name", "")
        last_updated = state["results"][0].get("last_updated", "")

    return {**state, "answer": answer, "source": source, "last_updated": last_updated}


async def log_conversation_node(state: ConsultantState) -> ConsultantState:
    """Registra la conversación en el log."""
    log_conversation(
        user_id=state["user_id"],
        agent_type="consultant",
        prompt=state["question"],
        response=state["answer"],
    )
    return state


# --- Construcción del grafo ---

def build_consultant_graph():
    graph = StateGraph(ConsultantState)

    graph.add_node("embed_question", embed_question_node)
    graph.add_node("search_documents", search_documents_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("log_conversation", log_conversation_node)

    graph.set_entry_point("embed_question")
    graph.add_edge("embed_question", "search_documents")
    graph.add_edge("search_documents", "generate_answer")
    graph.add_edge("generate_answer", "log_conversation")
    graph.add_edge("log_conversation", END)

    return graph.compile()


# --- Función principal ---

async def query_documents(question: str, user_id: str) -> dict:
    """
    Responde una pregunta en lenguaje natural usando documentación aprobada.

    Returns:
        dict con 'answer', 'source' y 'last_updated'.
    """
    graph = build_consultant_graph()

    initial_state: ConsultantState = {
        "question": question,
        "user_id": user_id,
        "query_embedding": [],
        "results": [],
        "context": "",
        "answer": "",
        "source": "",
        "last_updated": "",
        "error": None,
    }

    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        return {"error": final_state["error"]}

    return {
        "answer": final_state["answer"],
        "source": final_state["source"],
        "last_updated": final_state["last_updated"],
    }
