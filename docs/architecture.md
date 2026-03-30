# Arquitectura del sistema

## Visión general

memorIA tiene tres capas principales: una interfaz de chat (Next.js), una API REST (FastAPI) y un sistema de agentes (LangGraph). Los agentes consumen fuentes de datos externas via MCP y persisten todo en Supabase.

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend — Next.js 16                                      │
│  Chat + Viewer/Editor + Lista de documentos                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────────────┐
│  API — FastAPI                                              │
│  /chat  /documents  /spec  /consultant  /toolbox/objects    │
└──┬──────────┬──────────┬──────────────────────────────────┘
   │          │          │
   ▼          ▼          ▼
 Chat      Generator  Auditor / Consultant
 Agent     Agent      Agents
   │          │          │
   │     ┌────┴────┐      │
   │     │  MCP    │      │
   │     │ Clients │      │
   │     └────┬────┘      │
   │          │           │
   │     ┌────┴────┐      │
   │     │GenAI    │      │
   │     │Toolbox  │      │
   │     │Tableau  │      │
   │     └─────────┘      │
   │                      │
   └──────────────────────┴──────────────► Supabase
                                          documents
                                          document_embeddings
                                          audit_log / action_log
```

---

## Los cuatro agentes

### 1. Agente de Chat (`agents/chat_agent.py`)

Es el **orquestador**. Recibe todos los mensajes del usuario y decide qué hacer usando el patrón ReAct (Reasoning + Acting). Tiene seis herramientas:

| Herramienta | Cuándo la usa | Qué hace |
|---|---|---|
| `listar_objetos_disponibles` | El usuario quiere saber qué puede documentar | Consulta `/toolbox/objects` y devuelve una tabla |
| `crear_documentacion` | El usuario pide documentar algo | Llama al Generador y abre el panel lateral |
| `buscar_documentacion` | El usuario hace una pregunta sobre datos | Llama al Consultor RAG y abre el documento fuente |
| `listar_documentacion` | El usuario quiere ver documentos existentes | Lista documentos con filtros de estado y tipo |
| `abrir_documento` | El usuario quiere ver o editar un documento | Busca por nombre y abre el panel lateral |
| `auditar_documento` | El usuario quiere auditar un borrador | Envía a auditoría y abre el resultado en el panel |

El agente **no ejecuta** los otros agentes directamente — los invoca via HTTP contra la misma API. Esto permite que el proceso de generación sea independiente del timeout de la conexión SSE.

Cuando la herramienta `crear_documentacion` tiene éxito, setea `_pending_panel` en la respuesta. La UI lee ese campo y abre automáticamente el panel lateral con el documento recién generado.

### 2. Agente Generador (`agents/generator.py`)

Grafo lineal de tres nodos:

```
fetch_metadata → generate_draft → save_draft
```

**fetch_metadata**: Consulta el GenAI Toolbox (o Tableau MCP para dashboards) para obtener schema, datos de muestra, claves, índices y estadísticas del objeto.

**generate_draft**: Construye el prompt a partir del spec (`config/doc_spec.py`) e invoca Gemini 2.5 Flash. El modelo devuelve JSON estructurado con todos los campos del documento. Si la respuesta no es JSON válido, reintenta hasta 2 veces.

**save_draft**: Guarda el documento en Supabase con `status = 'draft'` y registra la acción en `action_log`.

### 3. Agente Auditor (`agents/auditor.py`)

Grafo con lógica condicional:

```
load_document → evaluate → update_status ──► [trigger_indexing] → END
                                         └──► END
```

**evaluate**: Construye el prompt con los `quality_criteria` de cada campo del spec (solo campos `PARCIAL` y `HUMANO` — los `AUTO` los genera el sistema y no se auditan). Pide a Gemini que evalúe y devuelve uno de dos resultados:

- `approved` → cambia status a `'approved'`, dispara indexación en pgvector
- `observations` → devuelve lista de issues concretos; el documento permanece en `draft`

No existe estado `rejected`. Un documento siempre puede ser corregido y re-auditado. Toda decisión queda registrada en `audit_log`.

### 4. Agente Consultor RAG (`agents/consultant.py`)

Grafo lineal de cuatro nodos:

```
embed_question → search_documents → generate_answer → log_conversation
```

Genera un embedding de la pregunta (Gemini `gemini-embedding-001`, 768 dimensiones), busca los documentos más similares en pgvector (distancia coseno, threshold 0.5), y para cada resultado recupera el **documento completo** desde la DB usando `document_to_full_context()` — que serializa todos los campos del spec del tipo de objeto correspondiente. El LLM responde basándose únicamente en ese contexto y devuelve JSON estructurado `{"answer": "...", "source": "nombre del documento"}`. El campo `source` es el nombre exacto que el LLM declara haber usado, no el resultado de mayor similitud vectorial, lo que permite abrir el documento correcto en el panel. Si no hay documentos relevantes, responde explícitamente que no encontró información.

---

## El spec como fuente de verdad

Todo el sistema gira en torno a `config/doc_spec.py`. Cuando el generador construye su prompt, cuando el auditor evalúa calidad, cuando el frontend muestra el editor, cuando el PDF se exporta — todos leen el mismo spec.

```
config/doc_spec.py
        │
        ├─► agents/prompts.py         (criterios para el generador)
        ├─► agents/auditor.py         (quality_criteria por campo)
        ├─► api/main.py               (GET /spec/{type} → frontend)
        ├─► api/pdf.py                (renderizado PDF)
        └─► frontend/components/      (viewer + editor, via /spec/{type})
```

Ver [doc-structure.md](doc-structure.md) para cómo modificar el spec.

---

## Indexación y RAG

Cuando un documento pasa a `approved`, el auditor dispara el indexer:

```
Auditor aprueba
      │
      ▼
workers/indexer.py::index_document()
      │
      ├─► Serializa content JSONB → texto plano
      ├─► Gemini embedding-001 → vector de 768 dims
      └─► INSERT en document_embeddings (pgvector)
```

El indexer también corre un job de reconciliación cada 6 horas para detectar y corregir inconsistencias (documentos aprobados sin embedding, embeddings huérfanos).

---

## Flujo de datos en el frontend

El frontend se comunica con la API de dos formas:

1. **SSE (Server-Sent Events)** para el chat en tiempo real — el endpoint `/chat` streamea tokens a medida que Gemini genera la respuesta.
2. **SWR hooks** para datos estáticos — specs cacheados 30 minutos, tipos de objeto cacheados 10 minutos.

El estado global (usuario, panel abierto, historial de chat) vive en un store Zustand (`frontend/lib/store.ts`). Cuando el agente setea `pending_panel`, el store lo detecta y abre el panel lateral con el documento correspondiente.
