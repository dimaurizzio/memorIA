"""
Generación de embeddings usando Gemini text-embedding-004 via Google AI Studio.
(Convierte texto en vectores de 768 dimensiones que capturan su significado semántico,
optimizados para tareas de recuperación y búsqueda semántica).
"""
import json
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

EMBEDDING_MODEL = "models/gemini-embedding-001"


def generate_embedding(text: str) -> list[float]:
    """Genera un embedding de 768 dimensiones para indexar un documento."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )
    return result.embeddings[0].values


def generate_query_embedding(text: str) -> list[float]:
    """Genera un embedding optimizado para búsqueda (query)."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768,
        ),
    )
    return result.embeddings[0].values


# ── Helpers de renderizado ────────────────────────────────────────────────────

def _get_nested(content: dict, path: str):
    obj = content
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _render_value(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return "Sí" if val else "No"
    if isinstance(val, list):
        if not val:
            return None
        if isinstance(val[0], dict):
            rows = []
            for item in val:
                parts = [f"{k}: {v}" for k, v in item.items() if v not in (None, "", [], False)]
                if parts:
                    rows.append("  - " + " | ".join(parts))
            return "\n".join(rows) if rows else None
        return ", ".join(str(v) for v in val if v)
    s = str(val).strip()
    return s if s else None


def _render_section_lines(section, content: dict) -> list[str]:
    """Renderiza los campos de una sección a lista de líneas de texto."""
    lines = []
    for field in section.fields:
        val = _get_nested(content, field.path)
        rendered = _render_value(val)
        if not rendered:
            continue
        label = field.path.split(".")[-1].replace("_", " ").title()
        if "\n" in rendered:
            lines.append(f"{label}:\n{rendered}")
        else:
            lines.append(f"{label}: {rendered}")
    return lines


# ── API pública ───────────────────────────────────────────────────────────────

def document_to_section_chunks(document: dict) -> dict[str, str]:
    """
    Divide el documento en chunks por sección del spec.
    Retorna {section_key: texto_de_la_sección}.

    Derivado automáticamente del spec: al agregar una nueva sección en doc_spec.py,
    se indexa sola sin tocar este módulo ni el indexer.
    """
    object_type = document.get("object_type", "")
    content = document.get("content") or {}
    name = document.get("name", "")
    header = f"Documento: {name} | Tipo: {object_type}"

    try:
        from config.doc_spec import get_spec
        spec_sections = get_spec(object_type)
    except Exception:
        return {"full": f"{header}\n{json.dumps(content, ensure_ascii=False, indent=2)}"}

    chunks = {}
    for section in spec_sections:
        lines = _render_section_lines(section, content)
        if lines:
            chunks[section.key] = f"{header}\n[{section.label}]\n" + "\n".join(lines)

    return chunks


def document_to_full_context(document: dict) -> str:
    """
    Serializa el documento completo a texto estructurado.
    Se usa para construir el contexto del LLM consultor en queries RAG.
    """
    chunks = document_to_section_chunks(document)
    if not chunks:
        name = document.get("name", "")
        object_type = document.get("object_type", "")
        return f"Documento: {name} | Tipo: {object_type}"
    return "\n\n".join(chunks.values())
