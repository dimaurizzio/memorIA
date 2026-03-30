"""
Cliente MCP para Tableau usando el SDK mcp de Python con transporte stdio.
Conecta al servidor oficial @tableau/mcp-server (proceso Node.js).

Si las variables TABLEAU_* no están configuradas, todas las funciones
retornan vacío sin lanzar excepciones (degradación elegante).
"""
import os
import json
from mcp import StdioServerParameters, stdio_client, ClientSession
from dotenv import load_dotenv

load_dotenv()

_REQUIRED_ENV = ["TABLEAU_SERVER_URL", "TABLEAU_TOKEN_NAME", "TABLEAU_TOKEN_VALUE"]


def tableau_available() -> bool:
    return all(os.getenv(v) for v in _REQUIRED_ENV)


async def _call_tool(tool_name: str, args: dict = {}) -> object:
    """Abre conexión stdio al MCP server de Tableau, ejecuta un tool y cierra."""
    # El servidor @tableau/mcp-server espera SERVER, TOKEN_NAME, TOKEN_VALUE
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@tableau/mcp-server"],
        env={
            **os.environ,
            "SERVER":    os.getenv("TABLEAU_SERVER_URL", ""),
            "PAT_NAME":  os.getenv("TABLEAU_TOKEN_NAME", ""),
            "PAT_VALUE": os.getenv("TABLEAU_TOKEN_VALUE", ""),
            # SITE solo es requerido para Tableau Cloud; en Server on-premise se omite
            **({ "SITE": site } if (site := os.getenv("TABLEAU_SITE")) else {}),
        },
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            text = result.content[0].text if result.content else "[]"
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text


async def list_tableau_dashboards() -> list[dict]:
    """Lista workbooks de Tableau mapeados como dashboards para el sistema."""
    if not tableau_available():
        return []
    try:
        raw = await _call_tool("list-workbooks")
    except Exception:
        return []
    items = raw if isinstance(raw, list) else raw.get("items", []) if isinstance(raw, dict) else []
    return [
        {
            "name": wb.get("name", ""),
            "type": "dashboard",
            "connection": "tableau",
            "database_name": os.getenv("TABLEAU_SERVER_URL", ""),
        }
        for wb in items
        if wb.get("name")
    ]


async def get_dashboard_metadata(dashboard_name: str) -> dict:
    """Obtiene metadata de un workbook por nombre. Retorna dict vacío si no disponible."""
    if not tableau_available():
        return {}
    try:
        raw = await _call_tool("list-workbooks", {"filter": f"name:eq:{dashboard_name}"})
        items = raw if isinstance(raw, list) else raw.get("items", []) if isinstance(raw, dict) else []
        if not items:
            return {}
        workbook_id = items[0].get("id") or items[0].get("luid") or items[0].get("workbookId")
        if not workbook_id:
            return items[0]
        details = await _call_tool("get-workbook", {"workbookId": workbook_id})
        return details if isinstance(details, dict) else {}
    except Exception:
        return {}
