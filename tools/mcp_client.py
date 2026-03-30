"""
Cliente para GenAI Toolbox usando el SDK oficial toolbox-langchain.
Expone las herramientas del toolbox como funciones Python para los agentes.
¡Oh Toodles! Mausqueherramienta Misteriosa!
"""
import os
from toolbox_langchain import ToolboxClient
from toolbox_core.protocol import Protocol
from dotenv import load_dotenv

load_dotenv()

TOOLBOX_URL = os.getenv("TOOLBOX_URL", "http://localhost:5000")


async def get_tools(toolset: str = "default"):
    """
    Retorna las herramientas del toolbox como objetos LangChain.
    IMPORTANTE: las tools deben usarse dentro del mismo contexto de cliente.
    Usar esta función solo para pasar tools al agente LangGraph, no para invocarlas manualmente.
    """
    client = ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST)
    return await client.aload_toolset(toolset)


def _parse_result(result) -> list:
    """Parsea el resultado del toolbox, que puede ser JSON, lista o string vacío."""
    import json
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, str):
        text = result.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return []
    return []


async def find_matching_objects(name: str) -> dict:
    """
    Busca el objeto por nombre en el toolbox con tolerancia a variaciones.

    Devuelve uno de:
      {"match": "ExactName"}           — coincidencia exacta (puede corregir el case)
      {"suggestions": ["A", "B", ...]} — nombres similares encontrados
      {"not_found": True}              — ninguna coincidencia
    """
    import difflib

    try:
        tables = await list_tables()
    except Exception:
        # Si el toolbox no responde, dejamos pasar para que el agente lo intente igual
        return {"match": name}

    if not tables:
        return {"not_found": True}

    lower_to_original = {t.lower(): t for t in tables}

    # Coincidencia exacta (ignorar case)
    if name.lower() in lower_to_original:
        return {"match": lower_to_original[name.lower()]}

    # Similitud difusa (cutoff 0.45 — permisivo pero no demasiado)
    close = difflib.get_close_matches(
        name.lower(), list(lower_to_original.keys()), n=5, cutoff=0.45
    )

    # También incluir los que contienen el nombre como substring
    partial = [
        orig for low, orig in lower_to_original.items()
        if name.lower() in low or low in name.lower()
    ]

    # Unir ambas listas sin duplicados, manteniendo orden
    seen = set()
    suggestions = []
    for t in [lower_to_original[c] for c in close] + partial:
        if t not in seen:
            seen.add(t)
            suggestions.append(t)

    if suggestions:
        return {"suggestions": suggestions[:6]}

    return {"not_found": True}


async def list_objects(object_type: str | None = None) -> list[dict]:
    """
    Retorna objetos disponibles en todas las fuentes de datos con metadata enriquecida.

    Cada objeto tiene: name, type, connection, database_name.
    Si object_type filtra por tipo; None o 'todos' devuelve todo.

    Para agregar una fuente nueva: agregar el tool en toolbox.yaml y/o
    crear un nuevo client en tools/ y concatenar resultados a `objects`.
    """
    objects: list[dict] = []

    # GenAI Toolbox (tablas y vistas SQL)
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        list_tool = next(t for t in tools if t.name == "list_tables")
        result = await list_tool.ainvoke({})
        rows = _parse_result(result)
    objects.extend(row for row in rows if isinstance(row, dict) and "name" in row)

    # Tableau (dashboards) — solo si se piden dashboards o todos los tipos
    if not object_type or object_type == "todos" or object_type == "dashboard":
        from tools.tableau_client import list_tableau_dashboards
        objects.extend(await list_tableau_dashboards())

    if object_type and object_type != "todos":
        type_map = {"view": "view", "table": "table", "dashboard": "dashboard"}
        db_type = type_map.get(object_type)
        if db_type:
            objects = [o for o in objects if o.get("type") == db_type]

    return objects


async def list_tables() -> list[str]:
    """Retorna solo los nombres de tablas y vistas (backward compat)."""
    objects = await list_objects()
    return [o["name"] for o in objects]


async def get_table_schema(table_name: str) -> list[dict]:
    """Retorna el schema de una tabla o vista (columnas, tipos, constraints)."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        schema_tool = next(t for t in tools if t.name == "get_table_schema")
        result = await schema_tool.ainvoke({"table_name": table_name})
        return _parse_result(result)


async def get_sample_data(table_name: str) -> list[dict]:
    """Retorna hasta 20 filas de muestra de una tabla o vista."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        sample_tool = next(t for t in tools if t.name == "get_sample_data")
        result = await sample_tool.ainvoke({"table_name": table_name})
        return _parse_result(result)


async def get_foreign_keys(table_name: str) -> list[dict]:
    """Retorna las foreign keys de una tabla."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        fk_tool = next(t for t in tools if t.name == "get_foreign_keys")
        result = await fk_tool.ainvoke({"table_name": table_name})
        return _parse_result(result)


async def get_indexes(table_name: str) -> list[dict]:
    """Retorna los índices de una tabla con sus columnas."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        idx_tool = next(t for t in tools if t.name == "get_indexes")
        result = await idx_tool.ainvoke({"table_name": table_name})
        return _parse_result(result)


async def get_row_count(table_name: str) -> int:
    """Retorna el conteo de filas de una tabla."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        count_tool = next(t for t in tools if t.name == "get_row_count")
        result = await count_tool.ainvoke({"table_name": table_name})
        rows = _parse_result(result)
        if rows and isinstance(rows[0], dict):
            return rows[0].get("row_count", 0)
        return 0


async def get_ddl(object_name: str) -> str:
    """Retorna la sentencia CREATE (DDL) de una tabla o vista."""
    async with ToolboxClient(TOOLBOX_URL, protocol=Protocol.MCP_LATEST) as client:
        tools = await client.aload_toolset("default")
        ddl_tool = next(t for t in tools if t.name == "get_ddl")
        result = await ddl_tool.ainvoke({"object_name": object_name})
        rows = _parse_result(result)
        if rows and isinstance(rows[0], dict):
            return rows[0].get("sql", "")
        return ""
