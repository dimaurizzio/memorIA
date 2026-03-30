# Modificar la estructura de un documento

La estructura de documentación está definida en `config/doc_spec.py`. Este archivo es la **fuente de verdad única** del sistema. Editarlo es la única forma de agregar, quitar o modificar campos — nada más necesita cambiarse.

---

## Qué se propaga automáticamente

Cuando editás `doc_spec.py`, estos componentes se actualizan solos:

| Componente | Cómo lo usa |
|---|---|
| `agents/prompts.py` | Lee el spec para construir el prompt del generador |
| `agents/auditor.py` | Lee `quality_criteria` de cada campo para evaluar calidad |
| `api/main.py` | Expone `GET /spec/{type}` — el frontend consume este endpoint |
| `api/pdf.py` | Lee el spec para renderizar el PDF en el mismo orden |
| `frontend/components/doc-viewer.tsx` | Recibe el spec via API y renderiza cada campo |
| `frontend/components/doc-inline-editor.tsx` | Muestra inputs editables según `completion` y `field_type` |

---

## Agregar un campo nuevo

### 1. Encontrá la sección correcta en `_SPECS`

El archivo define un `DocSpec` por tipo de objeto (`table`, `view`, `stored_procedure`, `dashboard`). Cada spec tiene secciones (`SectionSpec`) y cada sección tiene campos (`FieldSpec`).

### 2. Agregá el `FieldSpec`

```python
FieldSpec(
    path="governance.data_steward",   # ruta en el JSON del documento
    required=False,                    # ¿es obligatorio para aprobar?
    completion="HUMANO",               # quién lo completa (ver tabla abajo)
    quality_criteria="Nombre o alias del data steward responsable del dato.",
    user_help="Persona responsable de la calidad y definición del dato, puede ser diferente al owner técnico.",
    field_type="string",               # tipo de dato
),
```

### `completion` — quién completa el campo

| Valor | Significado | Qué hace el generador | Qué ve el usuario |
|---|---|---|---|
| `AUTO` | La IA lo completa completamente | Lo llena desde el schema | No aparece en el editor (read-only en viewer) |
| `PARCIAL` | La IA hace un borrador | Genera una propuesta | Badge `P` — aparece en editor para revisar |
| `HUMANO` | La IA no puede inferirlo | Lo deja vacío (placeholder) | Badge `H` — aparece en editor para completar |

### `field_type` — tipos soportados

| Tipo | Renderizado en viewer | Input en editor |
|---|---|---|
| `string` | Texto plano o bloque de código (si > 200 chars con saltos) | `<textarea>` |
| `boolean` | "Sí" / "No" | Toggle |
| `list[str]` | Tags con fondo gris | Input con opción de agregar tags |
| array de objetos | Tabla (≤4 columnas) o tarjetas (>4 columnas) | Editable: textareas para subfields de tipo `string`/`string\|null`; el resto es read-only |

---

## Agregar un campo array (lista de objetos)

Para campos que contienen múltiples filas (como `technical.fields` que lista todas las columnas):

```python
FieldSpec(
    path="technical.indexes",
    required=False,
    completion="AUTO",
    auto_source="PRAGMA index_list",
    field_type="array",
    is_array=True,
    item_fields=(
        ItemField("name", "string"),
        ItemField("unique", "boolean"),
        ItemField("columns", "string"),
    ),
),
```

Los arrays se renderizan:
- Con **≤ 4 `item_fields`** → tabla HTML estándar
- Con **> 4 `item_fields`** → lista de tarjetas verticales (evita overflow en A4)

Los arrays con `completion="PARCIAL"` muestran en el editor un card por ítem con textareas editables para los subfields de tipo `string` o `string | null` (ej: `description`, `business_name`, `value_domain`). Los subfields booleanos y los que actúan como identificador (el primer `ItemField`) son read-only. Los arrays con `completion="AUTO"` siguen siendo completamente read-only.

---

## Quitar un campo

Simplemente eliminá el `FieldSpec` de la sección correspondiente. Los documentos existentes en Supabase que tengan ese campo en su JSONB lo conservan, pero dejan de mostrarse en el viewer y el editor.

---

## Cambiar el orden de secciones o campos

El viewer y el PDF respetan el orden exacto en que están declarados en el spec. Reordenar los `FieldSpec` dentro de una `SectionSpec`, o reordenar las `SectionSpec` dentro de un `DocSpec`, cambia el orden visual automáticamente.

---

## Campos con valores válidos (enum)

Para campos con un conjunto cerrado de opciones válidas:

```python
FieldSpec(
    path="identification.sensitivity",
    required=True,
    completion="HUMANO",
    enum_key="sensitivity",   # clave en VALID_ENUMS al inicio del archivo
    user_help="Nivel de sensibilidad del dato.",
    field_type="string",
),
```

Los valores válidos están en `VALID_ENUMS` al inicio del archivo. El editor renderizará un `<select>` en lugar de un textarea.

---

## Verificar los cambios

Después de editar el spec, reiniciá la API para que cargue la versión nueva:

```bash
# Manual
uvicorn api.main:app --reload   # el reload lo hace automáticamente en dev

# Docker
docker compose restart api
```

Verificá el endpoint del spec para confirmar que el campo aparece:

```bash
curl http://localhost:8000/spec/table | python -m json.tool
```
