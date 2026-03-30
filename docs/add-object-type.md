# Agregar un nuevo tipo de objeto

Actualmente memorIA documenta cuatro tipos de objetos: `table`, `view`, `stored_procedure` y `dashboard`. Esta guía explica cómo agregar un nuevo tipo (por ejemplo, `api_endpoint` o `ml_model`).

---

## Resumen de cambios

| Archivo | Qué cambia |
|---|---|
| `config/doc_spec.py` | Definir el spec del nuevo tipo |
| `tools/toolbox_client.py` | (Opcional) Agregar instrucciones de fetch si el objeto requiere una fuente de datos distinta |
| `agents/prompts.py` | Agregar el prompt de sistema para el generador del nuevo tipo |
| `api/main.py` | Registrar el nuevo tipo en la lista de tipos válidos |

---

## Paso 1 — Definir el spec

En `config/doc_spec.py`, agregá un nuevo `DocSpec` al diccionario `_SPECS`:

```python
_SPECS["api_endpoint"] = DocSpec(
    object_type="api_endpoint",
    sections=(
        SectionSpec("identification", "Identificación y Contexto", fields=(
            FieldSpec("identification.physical_name", True, "AUTO",
                      auto_source="Nombre del endpoint"),
            FieldSpec("identification.business_name", True, "HUMANO",
                      quality_criteria="Nombre en lenguaje de negocio.",
                      user_help="¿Cómo se llama este endpoint en términos de negocio?"),
            FieldSpec("identification.business_domain", True, "HUMANO",
                      user_help="¿A qué área funcional pertenece?"),
            FieldSpec("identification.description", True, "PARCIAL",
                      quality_criteria="Mínimo 30 palabras.",
                      user_help="Qué hace este endpoint, cuándo usarlo.",
                      min_words=30),
        )),
        SectionSpec("technical", "Metadatos Técnicos", fields=(
            FieldSpec("technical.method", True, "AUTO",
                      auto_source="GET | POST | PUT | DELETE"),
            FieldSpec("technical.path", True, "AUTO",
                      auto_source="Ruta del endpoint"),
            FieldSpec("technical.parameters", False, "AUTO",
                      field_type="array",
                      is_array=True,
                      item_fields=(
                          ItemField("name", "string"),
                          ItemField("type", "string"),
                          ItemField("required", "boolean"),
                          ItemField("description", "string"),
                      )),
        )),
        SectionSpec("governance", "Gobernanza", fields=(
            FieldSpec("governance.technical_owner", True, "HUMANO",
                      quality_criteria="Email o alias. No puede ser igual a business_owner.",
                      user_help="Responsable técnico del endpoint."),
        )),
    )
)
```

Registrá el nuevo tipo en `VALID_ENUMS`:

```python
VALID_ENUMS: dict[str, list[str]] = {
    "object_type": ["table", "view", "stored_procedure", "dashboard", "api_endpoint"],
    ...
}
```

---

## Paso 2 — Agregar el prompt del generador

En `agents/prompts.py`, agregá el bloque de instrucciones específico para el nuevo tipo en la función `build_generator_prompt()`:

```python
TYPE_HINTS = {
    "table": "...",
    "view": "...",
    "stored_procedure": "...",
    "dashboard": "...",
    "api_endpoint": """
Este objeto es un endpoint de API REST.
- method, path y parameters los obtenés del schema OpenAPI o de la metadata provista.
- description debe explicar el propósito del endpoint en términos de negocio.
- Inferí el business_name a partir del path y el método.
""",
}
```

---

## Paso 3 — Registrar en la API

En `api/main.py`, la lista de tipos válidos se usa para validar el parámetro `object_type` en el endpoint de creación. Agregá el nuevo tipo:

```python
VALID_OBJECT_TYPES = {"table", "view", "stored_procedure", "dashboard", "api_endpoint"}
```

---

## Paso 4 — (Opcional) Fuente de datos personalizada

Si el nuevo tipo requiere una fuente de datos distinta al GenAI Toolbox (por ejemplo, un archivo OpenAPI), editá `tools/toolbox_client.py` para manejar el caso:

```python
async def fetch_metadata(object_type: str, object_name: str) -> dict:
    if object_type == "api_endpoint":
        return await fetch_openapi_metadata(object_name)
    # caso por defecto: GenAI Toolbox
    return await fetch_toolbox_metadata(object_type, object_name)
```

---

## Verificar

1. Reiniciá la API: `uvicorn api.main:app --reload`
2. Verificá que el spec está disponible: `curl http://localhost:8000/spec/api_endpoint`
3. Probá desde el chat: *"documentá el endpoint /api/v1/pedidos"*
4. El agente debería generar un borrador usando el nuevo spec

---

## Qué se propaga automáticamente

Una vez que el spec está definido, estos componentes funcionan sin cambios adicionales:

- El **viewer** renderiza los campos en el orden del spec
- El **editor** muestra inputs para los campos `HUMANO` y `PARCIAL`
- El **auditor** evalúa calidad usando los `quality_criteria` del spec
- El **PDF** se exporta con la misma estructura del viewer
- La **búsqueda RAG** indexa documentos del nuevo tipo junto con los demás
