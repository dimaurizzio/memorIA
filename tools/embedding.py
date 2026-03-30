"""
Generación de embeddings usando Gemini text-embedding-004 via Google AI Studio.
(Convierte texto en vectores de 768 dimensiones que capturan su significado semántico,
optimizados para tareas de recuperación y búsqueda semántica).
"""
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


def document_to_full_context(document: dict) -> str:
    """
    Serializa el documento completo a texto estructurado para el contexto del LLM consultor.
    Recorre TODOS los campos del spec del tipo de objeto — cubre todos los tipos soportados
    (table, view, dashboard, stored_procedure) con todos sus campos.
    Independiente de document_to_text (que se usa solo para generar embeddings).
    """
    import json as _json
    from config.doc_spec import get_spec

    object_type = document.get("object_type", "")
    content = document.get("content") or {}
    name = document.get("name", "")

    def _get(path: str):
        obj = content
        for key in path.split("."):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(key)
        return obj

    def _render(val) -> str | None:
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

    try:
        spec_sections = get_spec(object_type)
    except Exception:
        # Fallback para tipos no registrados: serializar el contenido completo
        return f"Documento: {name} ({object_type})\n{_json.dumps(content, ensure_ascii=False, indent=2)}"

    lines = [f"Documento: {name} | Tipo: {object_type}"]

    for section in spec_sections:
        section_lines = []
        for field in section.fields:
            val = _get(field.path)
            rendered = _render(val)
            if not rendered:
                continue
            label = field.path.split(".")[-1].replace("_", " ").title()
            if "\n" in rendered:
                section_lines.append(f"{label}:\n{rendered}")
            else:
                section_lines.append(f"{label}: {rendered}")
        if section_lines:
            lines.append(f"\n[{section.label}]")
            lines.extend(section_lines)

    return "\n".join(lines)


def document_to_text(document: dict) -> str:
    """
    Serializa un documento a texto plano para generar su embedding.
    Acepta el documento completo (con name/object_type en el top-level y
    content anidado según el spec-driven schema).
    """
    content = document.get("content") or {}

    def _nested(path: str) -> str:
        obj = content
        for key in path.split("."):
            if not isinstance(obj, dict):
                return ""
            obj = obj.get(key) or ""
        return str(obj) if obj else ""

    parts = [
        f"Nombre: {document.get('name', '')}",
        f"Tipo: {document.get('object_type', '')}",
        f"Dominio: {document.get('business_domain', '') or _nested('identification.business_domain')}",
    ]

    # Descripción — el path varía según el tipo de objeto
    description = (
        _nested("description.business_description")
        or _nested("description.purpose")
    )
    if description:
        parts.append(f"Descripción: {description}")

    # Campos (table / view)
    fields = (
        content.get("technical", {}).get("fields")
        or content.get("technical", {}).get("exposed_columns")
        or []
    )
    if fields:
        field_texts = [
            f"{f.get('physical_name', f.get('name', ''))} "
            f"({f.get('data_type', f.get('type', ''))}): {f.get('description', '')}"
            for f in fields
            if isinstance(f, dict)
        ]
        if field_texts:
            parts.append("Campos: " + ", ".join(filter(None, field_texts)))

    # Lógica de transformación (view / stored procedure)
    logic = (
        _nested("technical.transformation_logic")
        or _nested("sp_interface.transformation_logic")
    )
    if logic:
        parts.append(f"Lógica de transformación: {logic}")

    # Métricas (dashboard)
    metrics = content.get("dashboard", {}).get("metrics") or []
    if metrics:
        names = [m.get("name", "") for m in metrics if isinstance(m, dict) and m.get("name")]
        if names:
            parts.append("Métricas: " + ", ".join(names))

    return "\n".join(filter(None, parts))
