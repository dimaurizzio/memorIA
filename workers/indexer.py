"""
Worker de indexación RAG.

Responsabilidades:
- Cuando un documento pasa a 'approved': genera su embedding y lo inserta en document_embeddings
- Cuando un documento sale de 'approved': elimina su embedding
- Job de reconciliación cada 6 horas: asegura consistencia entre documents y document_embeddings

Este worker puede recibir webhooks HTTP cuando cambia el status de un documento.
También puede llamarse directamente desde el agente auditor.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException

from db.client import (
    get_document,
    list_documents,
    save_embedding,
    delete_embedding,
    list_embedding_document_ids,
)
from tools.embedding import generate_embedding, document_to_section_chunks

load_dotenv()

WEBHOOK_SECRET = os.getenv("APP_SECRET_KEY", "")

app = FastAPI(title="Indexer Worker")


# --- Lógica de indexación ---

async def index_document(document_id: str) -> None:
    """Genera un embedding por sección del spec y los guarda en document_embeddings."""
    document = get_document(document_id)
    if not document:
        print(f"[indexer] Documento {document_id} no encontrado.")
        return

    if document["status"] != "approved":
        print(f"[indexer] Documento {document_id} no está aprobado, saltando.")
        return

    chunks = document_to_section_chunks(document)
    if not chunks:
        print(f"[indexer] Documento {document_id} no generó chunks, saltando.")
        return

    # Eliminar chunks anteriores (re-indexación limpia)
    delete_embedding(document_id)

    for section_key, chunk_text in chunks.items():
        embedding = generate_embedding(chunk_text)
        save_embedding(document_id, section_key, embedding, chunk_text)

    print(f"[indexer] '{document['name']}' indexado — {len(chunks)} secciones.")


async def remove_from_index(document_id: str) -> None:
    """Elimina el embedding de un documento que dejó de estar aprobado."""
    delete_embedding(document_id)
    print(f"[indexer] Embedding eliminado para documento {document_id}.")


async def reconciliation_job() -> dict:
    """
    Verifica consistencia entre documents y document_embeddings.
    - Indexa documentos aprobados sin embedding
    - Elimina embeddings de documentos no aprobados

    Retorna un resumen de las acciones tomadas.
    """
    print(f"[indexer] Iniciando job de reconciliación: {datetime.now(timezone.utc).isoformat()}")

    # Obtener todos los documentos aprobados
    approved_docs = list_documents(status="approved")
    approved_ids = {doc["id"] for doc in approved_docs}

    # Obtener todos los document_ids que tienen embedding
    indexed_ids = list_embedding_document_ids()

    # Documentos aprobados sin embedding → indexar
    to_index = approved_ids - indexed_ids
    # Embeddings de documentos no aprobados → eliminar
    to_remove = indexed_ids - approved_ids

    for doc_id in to_index:
        await index_document(doc_id)

    for doc_id in to_remove:
        await remove_from_index(doc_id)

    summary = {
        "indexed": len(to_index),
        "removed": len(to_remove),
        "total_approved": len(approved_ids),
        "total_indexed_after": len(approved_ids),
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"[indexer] Reconciliación completa: {summary}")
    return summary


# --- Webhook de Supabase ---

@app.post("/webhook/document-status")
async def handle_status_change(request: Request):
    """
    Recibe webhooks de Supabase cuando cambia el status de un documento.
    Configurar en Supabase: Database → Webhooks → tabla documents → evento UPDATE
    """
    # Verificar secret
    secret = request.headers.get("x-webhook-secret", "")
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    # Supabase envía old_record y record en el payload
    old_record = payload.get("old_record", {})
    new_record = payload.get("record", {})

    old_status = old_record.get("status")
    new_status = new_record.get("status")
    document_id = new_record.get("id")

    if not document_id:
        return {"ok": True, "action": "ignored"}

    if new_status == "approved" and old_status != "approved":
        await index_document(document_id)
        return {"ok": True, "action": "indexed", "document_id": document_id}

    elif old_status == "approved" and new_status != "approved":
        await remove_from_index(document_id)
        return {"ok": True, "action": "removed", "document_id": document_id}

    return {"ok": True, "action": "no_change"}


@app.post("/reconcile")
async def trigger_reconciliation():
    """Endpoint para disparar manualmente el job de reconciliación."""
    summary = await reconciliation_job()
    return summary


# --- Loop de reconciliación periódica ---

async def reconciliation_loop(interval_hours: int = 6):
    """Corre el job de reconciliación cada N horas."""
    while True:
        await asyncio.sleep(interval_hours * 3600)
        await reconciliation_job()


if __name__ == "__main__":
    import uvicorn

    async def main():
        # Correr reconciliación inicial al arrancar
        await reconciliation_job()

        # Levantar el servidor de webhooks y el loop de reconciliación en paralelo
        config = uvicorn.Config(app, host="0.0.0.0", port=8001, log_level="info")
        server = uvicorn.Server(config)
        await asyncio.gather(
            server.serve(),
            reconciliation_loop(interval_hours=6),
        )

    asyncio.run(main())
