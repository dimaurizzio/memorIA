"""
Registro central de tipos de objetos documentables.

DERIVADO AUTOMÁTICAMENTE de config.doc_spec — no editar manualmente.
Para agregar un nuevo tipo o cambiar secciones, editar doc_spec.py.

Este módulo mantiene la misma API pública que antes (OBJECT_TYPES, SECTION_LABELS,
type_config(), type_names()) para compatibilidad con el resto del sistema.
"""
from config.doc_spec import get_spec, supported_types, get_section_labels as _spec_labels

# ── Mapeo de tipo → atributos de presentación ────────────────────────────────
# Solo label, display_name, icon y metadata_fetch se definen acá porque son
# atributos de UI/orquestación que no pertenecen al spec de documentación.

_TYPE_META: dict[str, dict] = {
    "table": {
        "label":          "TABLA",
        "display_name":   "Tabla",
        "icon":           "🗄️",
        "metadata_fetch": ["schema", "sample_data"],
    },
    "view": {
        "label":          "VISTA",
        "display_name":   "Vista",
        "icon":           "🔍",
        "metadata_fetch": ["schema", "sample_data"],
    },
    "dashboard": {
        "label":          "DASHBOARD",
        "display_name":   "Dashboard",
        "icon":           "📊",
        "metadata_fetch": ["tableau"],
    },
    "stored_procedure": {
        "label":          "STORED PROC",
        "display_name":   "Stored Procedure",
        "icon":           "⚙️",
        "metadata_fetch": [],
    },
}


def _build_sections(object_type: str) -> list[str]:
    """Extrae las section keys del spec en orden de aparición."""
    return [s.key for s in get_spec(object_type)]


def _build_object_types() -> dict[str, dict]:
    """Construye OBJECT_TYPES derivando sections de doc_spec."""
    result = {}
    for otype in supported_types():
        meta = _TYPE_META.get(otype, {
            "label": otype.upper(),
            "display_name": otype.replace("_", " ").title(),
            "icon": "📄",
            "metadata_fetch": [],
        })
        result[otype] = {
            **meta,
            "sections": _build_sections(otype),
        }
    return result


OBJECT_TYPES: dict[str, dict] = _build_object_types()


def _build_section_labels() -> dict[str, str]:
    """Unifica todos los section labels de todos los tipos."""
    labels: dict[str, str] = {}
    for otype in supported_types():
        labels.update(_spec_labels(otype))
    return labels


SECTION_LABELS: dict[str, str] = _build_section_labels()


def type_names() -> list[str]:
    """Lista de nombres de tipo válidos."""
    return list(OBJECT_TYPES.keys())


def type_config(object_type: str) -> dict:
    """Config de un tipo específico. Devuelve dict vacío si no existe."""
    return OBJECT_TYPES.get(object_type, {})
