"""
Endpoints de administración.
Requieren rol admin — validación simplificada para MVP.
"""
from fastapi import APIRouter, HTTPException
from api.models import OverrideRequest
from db.client import get_document, update_document, log_audit, log_action, list_audit_log
from workers.indexer import index_document, remove_from_index
from datetime import datetime, timezone

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/documents/{document_id}/override")
async def override_document_status(document_id: str, body: OverrideRequest):
    """
    Override manual del status de un documento (solo admin).
    Siempre registra en audit_log con approval_type='manual_override'.
    Se permite override a "approved" (aprobación manual) o "delisted" (dar de baja una documentación). No se puede volver a "draft" desde acá.
    """
    if body.new_status not in ("approved", "delisted"):
        raise HTTPException(status_code=400, detail="new_status debe ser 'approved' o 'delisted'")

    document = get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    previous_status = document["status"]

    # Actualizar documento
    update_data = {"status": body.new_status}
    if body.new_status == "approved":
        update_data["approved_by"] = body.overridden_by
        update_data["approved_at"] = datetime.now(timezone.utc).isoformat()
        update_data["is_manual_override"] = True
    elif body.new_status == "delisted":
        update_data["is_manual_override"] = True

    update_document(document_id, update_data)

    # Registrar en audit_log — obligatorio para override
    log_audit(
        document_id=document_id,
        user_id=body.overridden_by,
        previous_status=previous_status,
        new_status=body.new_status,
        approval_type="manual_override",
        notes=body.notes,
    )

    log_action(
        user_id=body.overridden_by,
        action="override",
        document_id=document_id,
        metadata={"previous_status": previous_status, "new_status": body.new_status},
    )

    # Manejar indexación según el nuevo status
    if body.new_status == "approved" and previous_status != "approved":
        await index_document(document_id)
    elif previous_status == "approved" and body.new_status != "approved":
        await remove_from_index(document_id)

    return {
        "ok": True,
        "document_id": document_id,
        "previous_status": previous_status,
        "new_status": body.new_status,
        "overridden_by": body.overridden_by,
    }


@router.get("/audit-log")
def get_audit_log(document_id: str | None = None):
    """Lista el audit log, opcionalmente filtrado por documento."""
    return list_audit_log(document_id=document_id)
