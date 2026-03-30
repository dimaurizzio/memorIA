# Conectar una base de datos (GenAI Toolbox)

memorIA usa **GenAI Toolbox** (de Google) como capa de abstracción para introspeccionar objetos de base de datos. El generador le consulta al Toolbox el schema, tipos de datos, claves y estadísticas del objeto antes de construir el prompt para Gemini.

---

## Cómo funciona

El Toolbox expone una API HTTP que recibe el nombre y tipo de un objeto y devuelve su metadata. El generador consulta ese endpoint en el paso `fetch_metadata`.

La configuración de qué bases de datos exponer vive en un archivo YAML que le pasás al binario del Toolbox.

---

## Agregar una nueva base de datos

### 1. Editá el archivo de configuración

El archivo de desarrollo está en `dev_data/toolbox_dev.yaml`. Para producción, creá un archivo separado.

Estructura del YAML:

```yaml
sources:
  - name: mi_base           # nombre interno, puede ser cualquier cosa
    kind: postgres          # postgres | mysql | sqlite | bigquery | spanner | alloydb
    connection:
      host: localhost
      port: 5432
      database: nombre_db
      user: usuario
      password: contraseña
```

Para SQLite (útil en desarrollo):

```yaml
sources:
  - name: northwind
    kind: sqlite
    connection:
      path: /app/dev_data/northwind.db
```

### 2. Especificá qué objetos exponer

Por defecto, el Toolbox expone todas las tablas y vistas del schema `public`. Podés restringirlo:

```yaml
sources:
  - name: mi_base
    kind: postgres
    connection:
      host: ...
    include:
      schemas: ["ventas", "finanzas"]   # solo estos schemas
      tables: ["pedidos", "clientes"]   # solo estas tablas (opcional)
    exclude:
      tables: ["tabla_interna_*"]       # excluir por patrón
```

### 3. Reiniciá el Toolbox

**Docker:**
```bash
docker compose restart toolbox
```

**Manual:**
```bash
toolbox --config dev_data/toolbox_dev.yaml
```

El Toolbox carga la configuración al arrancar. Verificá que levantó correctamente:
```bash
curl http://localhost:5000/health
```

---

## Bases de datos soportadas

| Base de datos | `kind` | Notas |
|---|---|---|
| PostgreSQL | `postgres` | Incluye Amazon RDS, Cloud SQL, Aurora |
| MySQL | `mysql` | Incluye Amazon RDS, Cloud SQL |
| SQLite | `sqlite` | Solo para desarrollo local |
| BigQuery | `bigquery` | Autenticación via Application Default Credentials |
| Cloud Spanner | `spanner` | Requiere project y instance |
| AlloyDB | `alloydb` | Igual que PostgreSQL |

Para BigQuery y Cloud Spanner, la autenticación usa las credenciales de GCP de la máquina (ADC). No se configura usuario/contraseña.

---

## Variables de entorno alternativas

Si preferís no hardcodear credenciales en el YAML, el Toolbox soporta variables de entorno:

```yaml
sources:
  - name: produccion
    kind: postgres
    connection:
      host: ${DB_HOST}
      port: ${DB_PORT}
      database: ${DB_NAME}
      user: ${DB_USER}
      password: ${DB_PASSWORD}
```

---

## Verificar que los objetos son visibles

Una vez que el Toolbox está corriendo con la nueva base de datos configurada, podés verificar que los objetos son visibles desde el chat:

```
Usuario: "¿qué puedo documentar?"
```

El agente consultará `/toolbox/objects` y listará todos los objetos introspectables. Los de la nueva base de datos deberían aparecer ahí.

---

## Stored procedures

Para documentar stored procedures, el Toolbox necesita acceso al catálogo del sistema. En PostgreSQL, el usuario de conexión necesita permiso de lectura en `information_schema` y `pg_catalog`.

```sql
GRANT USAGE ON SCHEMA information_schema TO usuario_toolbox;
GRANT SELECT ON ALL TABLES IN SCHEMA information_schema TO usuario_toolbox;
```
