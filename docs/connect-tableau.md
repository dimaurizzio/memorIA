# Conectar Tableau

memorIA puede documentar dashboards de Tableau usando el **Tableau MCP Server** (`@tableau/mcp-server`). El generador consulta el servidor MCP para obtener metadata del workbook: fuentes de datos, campos calculados, medidas, filtros y descripción del dashboard.

---

## Requisitos

- Node.js 18+ en la máquina donde corre la API (o en el contenedor `api` si usás Docker)
- Acceso a Tableau Server o Tableau Cloud
- Un **Personal Access Token** (PAT) de Tableau

---

## Configurar las variables de entorno

Agregá estas variables a tu `.env`:

```bash
TABLEAU_SERVER_URL=https://tu-servidor.tableau.com
TABLEAU_SITE=nombre-del-site          # Solo Tableau Cloud. Omitir en Server on-premise
TABLEAU_TOKEN_NAME=nombre-del-token
TABLEAU_TOKEN_VALUE=valor-del-token
```

**Tableau Server on-premise:** `TABLEAU_SITE` debe estar vacío o no declarado. El site por defecto en Server on-premise no tiene nombre.

**Tableau Cloud:** el site ID aparece en la URL de Tableau: `https://prod-useast-a.online.tableau.com/#/site/mi-site/`. El site ID es `mi-site`.

---

## Crear un Personal Access Token en Tableau

1. Iniciá sesión en Tableau Server o Cloud
2. Hacé clic en tu avatar (arriba a la derecha) → **Configuración de cuenta**
3. En la sección **Tokens de acceso personal**, hacé clic en **Crear nuevo token**
4. Dale un nombre descriptivo (ej: `memoria-api`) y copiá el valor — solo se muestra una vez

---

## Verificar la conexión

Una vez configuradas las variables, reiniciá la API y pedile al agente que liste los dashboards:

```
Usuario: "¿qué dashboards puedo documentar?"
```

Si Tableau está configurado correctamente, la lista incluirá los workbooks accesibles con el PAT.

---

## Cómo funciona internamente

El cliente MCP vive en `tools/tableau_mcp.py`. Cuando el generador detecta que el objeto a documentar es de tipo `dashboard`, usa este cliente en lugar del GenAI Toolbox.

El cliente lanza un proceso `npx @tableau/mcp-server` via stdio y se comunica con él usando el protocolo MCP. Esto significa que Node.js debe estar disponible en el PATH del proceso API.

El servidor MCP devuelve:
- Metadata del workbook (nombre, descripción, proyecto, propietario)
- Lista de hojas y dashboards
- Fuentes de datos conectadas
- Campos calculados y medidas con sus fórmulas
- Filtros y parámetros

---

## Docker

En el contenedor `api`, Node.js 20 ya está instalado (es un requisito del Dockerfile). No necesitás hacer nada adicional para que funcione en Docker.

Solo asegurate de que las variables `TABLEAU_*` estén en tu `.env` antes de correr `docker compose up`.

---

## Permisos necesarios en Tableau

El PAT necesita acceso de **lectura** a los workbooks que querés documentar. No necesita permisos de escritura ni de administración.

Si el workbook está en un proyecto con permisos restringidos, el usuario del PAT debe tener el permiso "Ver" en ese proyecto.
