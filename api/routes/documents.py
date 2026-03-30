"""
CRUD de documentos.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from api.models import GenerateRequest, AuditRequest
from db.client import get_document, list_documents, update_document, delete_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def get_documents(
    status: str | None = None,
    object_type: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
):
    """Lista documentos con filtros opcionales. Los drafts solo son visibles para admin o su creador."""
    docs = list_documents(status=status, object_type=object_type)
    if role != "admin":
        docs = [d for d in docs if d["status"] != "draft" or d.get("created_by") == user_id]
    return docs


@router.get("/{document_id}")
def get_one_document(document_id: str):
    """Retorna un documento por ID."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


@router.patch("/{document_id}")
def patch_document(document_id: str, data: dict):
    """Edita campos de un documento en estado draft."""
    from datetime import date
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if doc["status"] != "draft":
        raise HTTPException(status_code=400, detail="Solo se pueden editar documentos en estado draft")
    # Actualizar doc_last_updated en la sección governance (formato v2)
    if "content" in data and isinstance(data["content"], dict):
        data["content"].setdefault("governance", {})["doc_last_updated"] = date.today().isoformat()
    return update_document(document_id, data)


@router.get("/{document_id}/pdf")
def download_pdf(document_id: str):
    """Genera y devuelve el PDF del documento."""
    from api.pdf import generate_pdf
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    pdf_bytes = generate_pdf(doc)
    filename = f"{doc.get('name', document_id)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{document_id}")
def remove_document(document_id: str):
    """Elimina un documento."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    delete_document(document_id)
    return {"ok": True}
