"""
Endpoints de los agentes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agents.generator import generate_document
from agents.auditor import audit_document
from agents.consultant import query_documents
from tools.mcp_client import find_matching_objects
from config.object_types import type_config

router = APIRouter(tags=["agents"])


class GenerateRequest(BaseModel):
    object_type: str
    object_name: str
    created_by: str


class AuditRequest(BaseModel):
    audited_by: str


class QueryRequest(BaseModel):
    question: str
    user_id: str


@router.post("/documents/generate")
async def generate(body: GenerateRequest):
    """Lanza el agente generador para crear un borrador."""
    from db.client import list_documents

    all_docs = list_documents(object_type=body.object_type)
    name_lower = body.object_name.lower()

    # Auto-borrar rechazados del mismo objeto antes de crear uno nuevo
    from db.client import delete_document
    for doc in all_docs:
        if doc["name"].lower() == name_lower and doc["status"] == "rejected":
            delete_document(doc["id"])

    # Verificar si ya existe un documento para este objeto en estado draft o approved
    existing = [
        doc for doc in all_docs
        if doc["name"].lower() == name_lower
        and doc["status"] in ("draft", "approved")
    ]

    if existing:
        doc = existing[0]
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Ya existe un documento para '{body.object_name}' en estado '{doc['status']}'.",
                "document_id": doc["id"],
                "status": doc["status"],
            }
        )

    # Pre-validación: verificar que el objeto existe en la fuente de datos.
    # Solo aplica a tipos que consultan el toolbox (metadata_fetch no vacío).
    cfg = type_config(body.object_type)
    if cfg.get("metadata_fetch"):
        lookup = await find_matching_objects(body.object_name)
        if "not_found" in lookup:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "OBJECT_NOT_FOUND",
                    "object_name": body.object_name,
                    "suggestions": [],
                },
            )
        elif "suggestions" in lookup:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "AMBIGUOUS_OBJECT",
                    "object_name": body.object_name,
                    "suggestions": lookup["suggestions"],
                },
            )
        else:
            # Usar el nombre canónico (corrige el case)
            body = GenerateRequest(
                object_type=body.object_type,
                object_name=lookup["match"],
                created_by=body.created_by,
            )

    result = await generate_document(
        object_type=body.object_type,
        object_name=body.object_name,
        created_by=body.created_by,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/documents/{document_id}/audit")
async def audit(document_id: str, body: AuditRequest):
    """Lanza el agente auditor sobre un documento draft."""
    result = await audit_document(
        document_id=document_id,
        audited_by=body.audited_by,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


class RefreshRequest(BaseModel):
    requested_by: str


@router.post("/documents/{document_id}/refresh")
async def refresh(document_id: str, body: RefreshRequest):
    """
    Actualiza un documento aprobado corriendo el agente generador de nuevo.
    - Elimina el embedding del índice
    - Baja el status a draft
    - Regenera el contenido desde cero consultando el toolbox
    - Registra en audit_log
    """
    from db.client import get_document, update_document, delete_embedding, log_audit, log_action

    document = get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if document["status"] not in ("approved", "draft"):
        raise HTTPException(status_code=400, detail="Solo se pueden actualizar documentos en estado 'approved' o 'draft'")

    previous_status = document["status"]

    # Eliminar embedding si estaba aprobado
    if previous_status == "approved":
        delete_embedding(document_id)

    # Regenerar desde cero
    result = await generate_document(
        object_type=document["object_type"],
        object_name=document["name"],
        created_by=body.requested_by,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # El generate_document ya guardó un documento nuevo — pero acá queremos
    # actualizar el existente, no crear uno nuevo. Actualizamos el content.
    from db.client import delete_document
    new_doc_id = result["document_id"]
    new_content = result["content"]

    # Actualizar el documento original con el nuevo contenido y bajar a draft
    update_document(document_id, {
        "content": new_content,
        "status": "draft",
        "approved_at": None,
        "approved_by": None,
        "is_manual_override": False,
    })

    # Eliminar el documento duplicado que creó generate_document
    delete_document(new_doc_id)

    # Registrar en audit_log
    log_audit(
        document_id=document_id,
        user_id=body.requested_by,
        previous_status=previous_status,
        new_status="draft",
        approval_type="automatic",
        notes="Actualización solicitada por usuario — contenido regenerado desde fuente de datos.",
    )

    log_action(
        user_id=body.requested_by,
        action="refresh",
        document_id=document_id,
        metadata={"previous_status": previous_status},
    )

    return {
        "ok": True,
        "document_id": document_id,
        "previous_status": previous_status,
        "new_status": "draft",
        "content": new_content,
    }


@router.post("/consultant/query")
async def consultant_query(body: QueryRequest):
    """Consulta en lenguaje natural sobre documentación aprobada."""
    result = await query_documents(
        question=body.question,
        user_id=body.user_id,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result
