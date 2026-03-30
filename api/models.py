"""Modelos Pydantic para validación de requests y responses."""
from pydantic import BaseModel
from typing import Any


class GenerateRequest(BaseModel):
    object_type: str    # 'table' | 'view' | 'dashboard' | 'stored_procedure'
    object_name: str
    created_by: str


class AuditRequest(BaseModel):
    audited_by: str


class OverrideRequest(BaseModel):
    new_status: str     # 'approved' | 'rejected'
    notes: str
    overridden_by: str
