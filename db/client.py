"""
Cliente de base de datos — PostgreSQL con psycopg2.
Todos los accesos a la base de datos del sistema pasan por este módulo.
"""
import json
import os
import uuid as _uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL debe estar definido en .env")
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, url)
        # Registrar deserializador JSONB → dict automático
        conn = _pool.getconn()
        psycopg2.extras.register_default_jsonb(conn, globally=True)
        _pool.putconn(conn)
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _to_dict(row) -> dict:
    """Convierte una RealDictRow a dict plano, normalizando UUIDs a strings."""
    return {k: str(v) if isinstance(v, _uuid.UUID) else v for k, v in dict(row).items()}


# --- Documentos ---

def save_document(data: dict) -> dict:
    """Inserta un nuevo documento y retorna el registro creado."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO documents
                    (name, object_type, business_domain, status, owner, content, created_by)
                VALUES
                    (%(name)s, %(object_type)s, %(business_domain)s,
                     %(status)s, %(owner)s, %(content)s, %(created_by)s)
                RETURNING *
            """, {**data, "content": json.dumps(data["content"])})
            return _to_dict(cur.fetchone())


def get_document(document_id: str) -> dict | None:
    """Obtiene un documento por ID. Retorna None si no existe."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
            return _to_dict(row) if row else None


def list_documents(status: str | None = None, object_type: str | None = None) -> list[dict]:
    """Lista documentos con filtros opcionales por status y tipo."""
    conditions, params = [], []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if object_type:
        conditions.append("object_type = %s")
        params.append(object_type)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM documents {where} ORDER BY created_at DESC", params)
            return [_to_dict(row) for row in cur.fetchall()]


_UPDATABLE_COLUMNS = frozenset({
    "name", "object_type", "business_domain", "status", "owner",
    "content", "approved_at", "approved_by", "is_manual_override",
    "last_audit_issues",
})

def update_document(document_id: str, data: dict) -> dict:
    """Actualiza campos de un documento y retorna el registro actualizado."""
    invalid = set(data.keys()) - _UPDATABLE_COLUMNS
    if invalid:
        raise ValueError(f"Columnas no permitidas en update_document: {invalid}")
    set_parts, params = [], []
    for key, value in data.items():
        set_parts.append(f"{key} = %s")
        params.append(json.dumps(value) if key == "content" else value)
    params.append(document_id)
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE documents SET {', '.join(set_parts)} WHERE id = %s RETURNING *",
                params,
            )
            return _to_dict(cur.fetchone())


def save_audit_issues(document_id: str, issues: list) -> None:
    """Persiste los issues del último audit. Pasar lista vacía para limpiar."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET last_audit_issues = %s WHERE id = %s",
                (json.dumps(issues) if issues else None, document_id),
            )


def delete_document(document_id: str) -> None:
    """Elimina un documento y sus registros relacionados."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_log       WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM action_log      WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM conversation_log WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM document_embeddings WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM documents       WHERE id = %s", (document_id,))


# --- Audit log ---

def log_audit(document_id: str, user_id: str, previous_status: str | None,
              new_status: str, approval_type: str, notes: str | None = None) -> None:
    """Registra un cambio de estado en el audit log."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_log
                    (document_id, user_id, previous_status, new_status, approval_type, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (document_id, user_id, previous_status, new_status, approval_type, notes))


def list_audit_log(document_id: str | None = None) -> list[dict]:
    """Lista el audit log, opcionalmente filtrado por documento."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if document_id:
                cur.execute(
                    "SELECT * FROM audit_log WHERE document_id = %s ORDER BY created_at DESC",
                    (document_id,),
                )
            else:
                cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC")
            return [_to_dict(row) for row in cur.fetchall()]


# --- Action log ---

def log_action(user_id: str, action: str, document_id: str | None = None,
               metadata: dict | None = None) -> None:
    """Registra una acción de usuario en el action log."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO action_log (user_id, action, document_id, metadata)
                VALUES (%s, %s, %s, %s)
            """, (user_id, action, document_id,
                  json.dumps(metadata) if metadata else None))


# --- Conversation log ---

def log_conversation(user_id: str, agent_type: str, prompt: str, response: str,
                     document_id: str | None = None) -> None:
    """Registra una interacción con un agente en el conversation log."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversation_log
                    (user_id, agent_type, document_id, prompt, response)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, agent_type, document_id, prompt, response))


# --- Embeddings ---

def save_embedding(document_id: str, section_key: str, embedding: list[float], content_text: str) -> None:
    """Inserta o actualiza el embedding de un chunk (sección) de documento aprobado."""
    vec = "[" + ",".join(map(str, embedding)) + "]"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_embeddings (document_id, section_key, embedding, content_text)
                VALUES (%s, %s, %s::vector, %s)
                ON CONFLICT (document_id, section_key) DO UPDATE
                  SET embedding = EXCLUDED.embedding,
                      content_text = EXCLUDED.content_text
            """, (document_id, section_key, vec, content_text))


def delete_embedding(document_id: str) -> None:
    """Elimina el embedding de un documento."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_embeddings WHERE document_id = %s", (document_id,)
            )


def list_embedding_document_ids() -> set[str]:
    """Retorna el conjunto de document_ids que tienen embedding (para reconciliación)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT document_id FROM document_embeddings")
            return {str(row[0]) for row in cur.fetchall()}


def search_documents(query_embedding: list[float], match_count: int = 5,
                     similarity_threshold: float = 0.7) -> list[dict]:
    """Busca documentos similares usando la función pgvector definida en el schema."""
    vec = "[" + ",".join(map(str, query_embedding)) + "]"
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM search_documents(%s::vector, %s, %s)",
                (vec, match_count, similarity_threshold),
            )
            return [_to_dict(row) for row in cur.fetchall()]
