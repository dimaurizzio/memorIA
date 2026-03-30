# Flujo de usuario

## Visión general

El usuario interactúa exclusivamente con el chat. El agente de chat es el orquestador: interpreta la intención del mensaje y decide qué herramienta invocar.

---

## 1. Documentar un objeto nuevo

### Paso 1 — El usuario pide documentar

```
Usuario: "documentá la tabla ventas_detalle"
```

El agente detecta el nombre y tipo del objeto. Si el nombre es ambiguo, consulta la lista de objetos disponibles y pregunta.

### Paso 2 — El generador entra en acción

El agente invoca la herramienta `crear_documentacion`, que llama al endpoint `/documents` con el nombre y tipo del objeto.

El **Agente Generador** ejecuta tres pasos internos:

1. **`fetch_metadata`** — consulta el GenAI Toolbox (o Tableau MCP para dashboards) y obtiene: schema completo, tipos de dato, claves primarias/foráneas, índices, estadísticas de volumen y ejemplos de datos.

2. **`generate_draft`** — construye un prompt con el spec del documento y envía todo a Gemini 2.5 Flash. El modelo devuelve JSON estructurado con todos los campos del documento que puede inferir automáticamente.

3. **`save_draft`** — guarda el documento en Supabase con `status = 'draft'` y registra la acción en `action_log`.

### Paso 3 — El panel lateral se abre

El agente de chat recibe el ID del documento recién creado y lo comunica al frontend via `_pending_panel`. El store Zustand detecta el cambio y abre automáticamente el panel lateral mostrando el documento en modo viewer.

El chat confirma: *"Generé el borrador de ventas_detalle. Podés revisarlo en el panel."*

---

## 2. Revisar y completar el borrador

El documento llega con todos los campos `AUTO` completados (nombre físico, tipo, campos, claves). Los campos `PARCIAL` tienen un borrador generado por la IA que puede o no ser correcto. Los campos `HUMANO` aparecen vacíos con un placeholder.

El usuario puede:

- **Leer el documento** en el panel (modo viewer, solo lectura)
- **Editar el documento** — hace clic en "Editar" y el panel cambia al modo editor

En el **modo editor**:
- Los campos de texto se convierten en inputs inline
- Los campos booleanos se convierten en toggles
- Los arrays (campos de tabla, métricas, etc.) se muestran como read-only con el label "Generado automáticamente"
- Cada campo `HUMANO` o `PARCIAL` tiene un ícono `?` que al hacer hover muestra el `user_help` del spec — una explicación amigable de qué se espera en ese campo

El usuario completa los campos faltantes y hace clic en "Guardar".

---

## 3. Auditar el documento

Una vez satisfecho con el borrador, el usuario pide la auditoría:

```
Usuario: "auditá el documento de ventas_detalle"
```

El agente invoca la herramienta `auditar_documento`. El **Agente Auditor** evalúa cada campo contra los `quality_criteria` del spec y devuelve uno de tres resultados:

### `approved` ✅

- El documento cambia a `status = 'approved'`
- Se dispara automáticamente el indexer: Gemini genera un embedding de 768 dimensiones del contenido y lo inserta en `document_embeddings` (pgvector)
- A partir de ese momento, el documento está disponible para consultas RAG
- El chat confirma: *"El documento fue aprobado e indexado."*

### `observations` 🟡

- El auditor devuelve una lista concreta de issues (campo X está vacío, descripción Y es demasiado genérica, etc.)
- El usuario vuelve al editor, corrige los issues y repite el ciclo

### `rejected` ❌

- El auditor explica qué está fundamentalmente incompleto o incorrecto
- El usuario puede optar por regenerar el documento o editarlo manualmente desde cero

---

## 4. Consultar documentación existente

```
Usuario: "¿qué granularidad tiene la tabla pedidos?"
Usuario: "¿quién es el owner técnico del dashboard de ventas?"
```

El agente detecta que es una pregunta de consulta e invoca `buscar_documentacion`. El **Agente Consultor RAG**:

1. Genera un embedding de la pregunta
2. Busca en pgvector los documentos más similares (threshold coseno 0.5)
3. Responde basándose **únicamente** en los documentos encontrados

Si no hay documentos aprobados relevantes, responde explícitamente que no encontró información — nunca inventa.

---

## 5. Explorar qué objetos están disponibles

```
Usuario: "¿qué puedo documentar?"
```

El agente invoca `listar_objetos_disponibles`, consulta el endpoint `/toolbox/objects` y devuelve una tabla con todos los objetos introspectables (tablas, vistas, stored procedures, dashboards conectados).

---

## Estados del documento

| Status | Descripción | Siguiente acción |
|---|---|---|
| `draft` | Borrador generado o en edición | Completar campos, pedir auditoría |
| `approved` | Aprobado y disponible en RAG | — |
| `rejected` | Rechazado por el auditor | Regenerar o editar desde cero |

Un admin puede cambiar el status manualmente desde la lista de documentos, pero eso queda registrado en `audit_log` como `approval_type = 'manual_override'`.
