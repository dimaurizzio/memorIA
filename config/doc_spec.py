"""
Fuente de verdad del sistema de documentacion.

Este modulo es la representacion ejecutable de documentation_structure.md.
TODO el sistema (prompts, validaciones, frontend, viewer, editor) se deriva de aca.

Para agregar/quitar un campo de documentacion:
  1. Edita la seccion correspondiente en _SPECS.
  2. Listo. Los prompts del generador, los criterios del auditor, el JSON schema
     y la configuracion del frontend se adaptan automaticamente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence
import json

# ── Enums validos ────────────────────────────────────────────────────────────

VALID_ENUMS: dict[str, list[str]] = {
    "object_type":    ["table", "view", "stored_procedure", "dashboard"],
    "sensitivity":    ["public", "internal", "confidential", "restricted"],
    "object_status":  ["active", "deprecated", "migrating", "historical", "experimental"],
    "load_mode":      ["incremental", "full_refresh", "append_only", "near_realtime", "streaming"],
    "view_type":      ["simple", "join", "aggregated", "materialized", "rls"],
    "dashboard_type": ["strategic", "tactical", "operational", "self-service"],
    "table_subtype":  ["fact", "dimension", "staging", "lookup", "config", "log", "aggregated", "intermediate"],
    "sp_subtype":     ["data_transformation", "etl_load", "business_calculation",
                       "validation", "maintenance", "external_integration"],
}


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ItemField:
    """Describe un sub-campo dentro de un array (fields[], metrics[], etc.)."""
    name: str
    type: str  # "string", "boolean", "string | null", etc.


@dataclass(frozen=True)
class FieldSpec:
    """Especificacion completa de un campo de documentacion."""
    path: str                       # ruta en el JSON: "identification.physical_name"
    required: bool                  # REQ (True) vs OPT (False)
    completion: str                 # "AUTO" | "PARCIAL" | "HUMANO"
    auto_source: str = ""           # fuente automatica: "PRAGMA table_info", etc.
    quality_criteria: str = ""      # texto del criterio de calidad (para auditor)
    user_help: str = ""             # explicacion amigable para usuario final (en tooltips)
    min_words: int = 0              # minimo de palabras (0 = sin minimo)
    must_not_contain: tuple[str, ...] = ()  # frases prohibidas
    enum_key: str = ""              # clave en VALID_ENUMS si aplica
    is_array: bool = False          # True si el campo es un array de objetos
    item_fields: tuple[ItemField, ...] = ()  # sub-campos del array
    field_type: str = "string"      # "string", "boolean", "string | null", "list[str]"


@dataclass(frozen=True)
class SectionSpec:
    """Agrupacion de campos en una seccion del documento."""
    key: str            # "identification", "technical", "lineage", etc.
    label: str          # "Identificacion y Contexto"
    fields: tuple[FieldSpec, ...]


# ── Item schemas reutilizables ───────────────────────────────────────────────

_FIELD_ITEMS = (
    ItemField("physical_name", "string"),
    ItemField("business_name", "string"),
    ItemField("data_type", "string"),
    ItemField("nullable", "boolean"),
    ItemField("description", "string"),
    ItemField("value_domain", "string | null"),
    ItemField("is_pk", "boolean"),
    ItemField("is_fk", "boolean"),
    ItemField("fk_reference", "string | null"),
    ItemField("is_calculated", "boolean"),
    ItemField("formula", "string | null"),
)

_METRIC_ITEMS = (
    ItemField("name", "string"),
    ItemField("definition", "string"),
    ItemField("formula", "string"),
    ItemField("source", "string"),
    ItemField("periodicity", "string"),
    ItemField("implicit_filters", "list[str]"),
)

_PARAM_ITEMS = (
    ItemField("name", "string"),
    ItemField("data_type", "string"),
    ItemField("description", "string"),
    ItemField("required", "boolean"),
    ItemField("default_value", "string | null"),
    ItemField("valid_domain", "string | null"),
)

_EXPOSED_COL_ITEMS = (
    ItemField("physical_name", "string"),
    ItemField("business_name", "string"),
    ItemField("data_type", "string"),
    ItemField("nullable", "boolean"),
    ItemField("description", "string"),
    ItemField("is_calculated", "boolean"),
    ItemField("formula", "string | null"),
)


# ── Registro por tipo ────────────────────────────────────────────────────────

_SPECS: dict[str, tuple[SectionSpec, ...]] = {

    # ═══════════════════════════════════════════════════════════════════════
    # TABLE
    # ═══════════════════════════════════════════════════════════════════════
    "table": (
        SectionSpec("identification", "Identificacion y Contexto", (
            FieldSpec("identification.physical_name", True, "AUTO",
                      auto_source="PRAGMA table_info / INFORMATION_SCHEMA.TABLES",
                      quality_criteria="Nombre exacto, caracter por caracter."),
            FieldSpec("identification.business_name", True, "PARCIAL",
                      quality_criteria="Sin guiones bajos ni abreviaturas. Ej: 'Transacciones de Venta'.",
                      user_help="Nombre en lenguaje natural que entienda cualquier persona del negocio (sin caracteres técnicos)."),
            FieldSpec("identification.schema_database", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.TABLES",
                      quality_criteria="Formato: {ambiente}.{schema}.{tabla}."),
            FieldSpec("identification.object_type", True, "AUTO",
                      quality_criteria="Siempre 'table'."),
            FieldSpec("identification.subtype", True, "PARCIAL",
                      enum_key="table_subtype",
                      quality_criteria="Inferir por nombre y estructura.",
                      user_help="Clasificación técnica: ¿Qué tipo de tabla es? (fact=hechos/transacciones, dimension=contexto, staging=datos crudos)."),
            FieldSpec("identification.business_domain", True, "HUMANO",
                      quality_criteria="Area funcional de negocio. No el area de TI.",
                      user_help="¿A qué área de negocio pertenece? (ej: Ventas, Marketing, Finanzas, Operaciones, Logística)."),
            FieldSpec("identification.subdomain", False, "HUMANO",
                      field_type="string | null",
                      quality_criteria="Subdivision del dominio cuando aplica.",
                      user_help="Área más específica dentro del dominio (opcional). Ej: Ventas Online, Ventas Presenciales."),
            FieldSpec("identification.sensitivity", True, "PARCIAL",
                      enum_key="sensitivity",
                      quality_criteria="IA detecta PII por nombres de campo. El humano decide.",
                      user_help="¿Qué tan sensibles son los datos? Public=abiertos, Internal=solo dentro, Confidential=restringido, Restricted=muy sensible."),
        )),
        SectionSpec("description", "Descripcion de Negocio", (
            FieldSpec("description.business_description", True, "PARCIAL",
                      min_words=30,
                      must_not_contain=("contiene datos de", "almacena informacion sobre", "tabla que guarda", "contiene informacion de"),
                      quality_criteria="Debe responder: que es, para que sirve, quien la consume.",
                      user_help="Explica en palabras simples: qué información tiene esta tabla, para qué sirve y quién la usa."),
            FieldSpec("description.granularity", True, "PARCIAL",
                      quality_criteria="Una fila representa... Obligatorio en tablas tipo 'fact'.",
                      user_help="¿Qué representa cada fila? (ej: una transacción, un cliente, un día de ventas)."),
            FieldSpec("description.use_cases", True, "HUMANO",
                      field_type="list[str]",
                      quality_criteria="Minimo 2. Formato: 'Quien usa + para que decision'.",
                      user_help="Ejemplos concretos de cómo se usa. Ej: 'Finanzas para reportes mensuales', 'Marketing para analizar campañas'."),
            FieldSpec("description.audience", True, "HUMANO",
                      field_type="list[str]",
                      quality_criteria="Roles o equipos, no personas individuales.",
                      user_help="¿Qué equipos o roles necesitan acceso a esta tabla? Ej: Analistas, Data Scientists, CFO."),
        )),
        SectionSpec("technical", "Metadata Tecnico", (
            FieldSpec("technical.fields", True, "PARCIAL",
                      is_array=True, item_fields=_FIELD_ITEMS,
                      auto_source="PRAGMA table_info extrae nombre/tipo/nullable. IA genera descripciones.",
                      min_words=10,
                      quality_criteria="Ningun campo sin descripcion. Min 10 palabras por descripcion. FKs indican tabla referenciada.",
                      user_help="Lista de columnas: nombre técnico, tipo de dato, descripción clara, si es clave."),
            FieldSpec("technical.primary_key", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.TABLE_CONSTRAINTS / PRAGMA table_info",
                      field_type="string | null",
                      quality_criteria="Nombre exacto del campo o combinacion."),
            FieldSpec("technical.foreign_keys", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS / PRAGMA foreign_key_list",
                      field_type="list[str]",
                      quality_criteria="Formato: campo_local -> esquema.tabla.campo."),
            FieldSpec("technical.indexes", False, "AUTO",
                      auto_source="PRAGMA index_list",
                      field_type="list[str]",
                      quality_criteria="Solo indices no triviales que impactan performance."),
            FieldSpec("technical.partitioning", False, "PARCIAL",
                      auto_source="DDL o metadata del warehouse",
                      field_type="string | null",
                      quality_criteria="Campo y estrategia de particion. Si no hay particionamiento, indicar 'Sin particionamiento'.",
                      user_help="¿Cómo está particionada la tabla? (ej: por fecha de ingesta, por país). Si no aplica, escribí 'Sin particionamiento'."),
            FieldSpec("technical.approximate_size", False, "AUTO",
                      auto_source="COUNT(*) + metadata de storage",
                      field_type="string | null",
                      quality_criteria="Orden de magnitud. Ej: '~50M filas, ~8 GB'."),
        )),
        SectionSpec("lineage", "Linaje y Origen", (
            FieldSpec("lineage.source_system", True, "HUMANO",
                      quality_criteria="Nombre del sistema, modulo y tecnologia.",
                      user_help="¿De dónde vienen los datos? Nombre del sistema original. Ej: SAP - Módulo SD, Salesforce CRM."),
            FieldSpec("lineage.etl_pipeline", True, "PARCIAL",
                      quality_criteria="Nombre exacto del pipeline en la herramienta ETL.",
                      user_help="¿Qué proceso/pipeline ETL carga los datos? Nombre exacto en tu herramienta (Airflow, DBT, etc.)."),
            FieldSpec("lineage.refresh_frequency", True, "HUMANO",
                      quality_criteria="Periodicidad + horario + timezone.",
                      user_help="¿Con qué frecuencia se actualiza? Ej: Diariamente a las 02:00 UTC, Cada hora."),
            FieldSpec("lineage.load_mode", True, "PARCIAL",
                      enum_key="load_mode",
                      quality_criteria="Inferir del nombre del pipeline.",
                      user_help="¿Cómo se carga? Full refresh=borra y recarga todo, Incremental=solo cambios, Append=agrega nuevos."),
            FieldSpec("lineage.data_latency", True, "HUMANO",
                      quality_criteria="Tiempo desde evento en origen hasta disponibilidad.",
                      user_help="¿Cuánto retraso hay en los datos? Ej: 2 horas, Tiempo real, 1 día de atraso."),
            FieldSpec("lineage.upstream_tables", False, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Solo las inmediatamente anteriores en el linaje.",
                      user_help="¿De qué tablas se alimenta? Lista de tablas inmediatamente anteriores en la cadena de datos."),
            FieldSpec("lineage.downstream_tables", False, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Tablas o vistas que consumen esta tabla.",
                      user_help="¿Quién usa esta tabla? Tablas o vistas que dependen de ésta para funcionar."),
        )),
        SectionSpec("governance", "Gobernanza y Ciclo de Vida", (
            FieldSpec("governance.technical_owner", True, "HUMANO",
                      quality_criteria="Email o alias de equipo. No puede ser igual a business_owner.",
                      user_help="Dueño técnico responsable de mantener la tabla. La persona/equipo a contactar si algo falla."),
            FieldSpec("governance.business_owner", True, "HUMANO",
                      quality_criteria="Email o alias de equipo. No puede ser igual a technical_owner.",
                      user_help="Responsable de negocio. La persona/equipo que entiende por qué existe y cómo usarla."),
            FieldSpec("governance.creation_date", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.TABLES.CREATE_TIME",
                      field_type="string | null",
                      quality_criteria="Formato ISO 8601."),
            FieldSpec("governance.doc_last_updated", True, "AUTO",
                      auto_source="Plataforma automatica",
                      quality_criteria="Formato ISO 8601. Observacion si supera 90 dias."),
            FieldSpec("governance.object_status", True, "HUMANO",
                      enum_key="object_status",
                      quality_criteria="Estado actual del objeto.",
                      user_help="¿En qué estado está? Active=en uso, Deprecated=dejar de usar, Experimental=pruebas."),
            FieldSpec("governance.data_retention", True, "HUMANO",
                      quality_criteria="Indicar por cuánto tiempo se retienen los datos. Aceptar cualquier respuesta concreta: duración estimada, política informal, o 'Sin definir'. No exigir política formal de archivado.",
                      user_help="¿Por cuánto tiempo guardamos los datos? Ej: 5 años en BD, después archivar en S3."),
            FieldSpec("governance.access_policy", True, "PARCIAL",
                      quality_criteria="Grupos/roles de lectura y escritura. No personas individuales.",
                      user_help="¿Quién puede acceder? Especifica grupos/roles de lectura y escritura. Ej: Analistas (lectura), Admins (lectura+escritura)."),
            FieldSpec("governance.contains_pii", True, "PARCIAL",
                      field_type="boolean",
                      quality_criteria="IA detecta campos con nombres tipicos (email, dni, phone, address)."),
            FieldSpec("governance.pii_details", False, "HUMANO",
                      field_type="string | null",
                      quality_criteria="Si contains_pii es true, incluir que campos y base legal.",
                      user_help="Si tiene datos sensibles (emails, DNI, teléfonos), indica cuáles campos y por qué los necesitamos."),
            FieldSpec("governance.recent_changes", False, "HUMANO",
                      field_type="string | null",
                      quality_criteria="Cambios estructurales o semanticos en los ultimos 6 meses.",
                      user_help="¿Qué ha cambiado recientemente? Nuevas columnas, datos que cambieron de significado, etc."),
        )),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # VIEW
    # ═══════════════════════════════════════════════════════════════════════
    "view": (
        SectionSpec("identification", "Identificacion y Contexto", (
            FieldSpec("identification.physical_name", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.VIEWS",
                      quality_criteria="Nombre exacto."),
            FieldSpec("identification.business_name", True, "PARCIAL",
                      quality_criteria="Sin guiones bajos ni abreviaturas.",
                      user_help="Nombre en lenguaje natural que entienda cualquier persona del negocio."),
            FieldSpec("identification.schema_database", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.VIEWS",
                      quality_criteria="Formato: {ambiente}.{schema}.{vista}."),
            FieldSpec("identification.object_type", True, "AUTO",
                      quality_criteria="Siempre 'view'."),
            FieldSpec("identification.business_domain", True, "HUMANO",
                      quality_criteria="Area funcional de negocio.",
                      user_help="¿A qué área de negocio pertenece?"),
            FieldSpec("identification.sensitivity", True, "PARCIAL",
                      enum_key="sensitivity",
                      quality_criteria="IA sugiere basandose en tablas base. El humano decide.",
                      user_help="¿Qué tan sensibles son los datos que expone esta vista?"),
        )),
        SectionSpec("description", "Proposito y Logica", (
            FieldSpec("description.purpose", True, "PARCIAL",
                      min_words=25,
                      quality_criteria="Por que existe, que problema resuelve, por que usar esta vista.",
                      user_help="Explica qué problema resuelve esta vista y cuándo usarla en lugar de las tablas base."),
            FieldSpec("description.use_cases", True, "HUMANO",
                      field_type="list[str]",
                      quality_criteria="Dashboards, reportes o modelos que consumen esta vista.",
                      user_help="¿Quién usa esta vista? Dashboards, reportes, modelos analytics que dependen de ella."),
        )),
        SectionSpec("technical", "Metadata Tecnico", (
            FieldSpec("technical.view_type", True, "PARCIAL",
                      enum_key="view_type",
                      quality_criteria="Analizar DDL de la vista.",
                      user_help="¿Qué tipo de vista? Simple=una tabla, Join=combina tablas, Aggregated=suma/agrupa."),
            FieldSpec("technical.transformation_logic", True, "PARCIAL",
                      min_words=15,
                      quality_criteria="Descripcion en prosa de joins, filtros, calculos. No pegar el SQL.",
                      user_help="Explica en palabras simples: qué tablas combina, qué filtros aplica, qué cálculos hace."),
            FieldSpec("technical.exposed_columns", True, "PARCIAL",
                      is_array=True, item_fields=_EXPOSED_COL_ITEMS,
                      auto_source="INFORMATION_SCHEMA.COLUMNS",
                      quality_criteria="Cada columna necesita descripcion min 8 palabras. Calculadas incluyen formula.",
                      user_help="Las columnas que expone esta vista: nombre, tipo de dato, descripción clara."),
            FieldSpec("technical.implicit_filters", True, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Filtros WHERE que la vista aplica siempre. Causa de malinterpretaciones.",
                      user_help="Filtros que esta vista aplica automáticamente. Ej: solo datos del 2024, solo clientes activos."),
        )),
        SectionSpec("lineage", "Linaje y Dependencias", (
            FieldSpec("lineage.base_tables", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.VIEW_TABLE_USAGE / analisis DDL",
                      field_type="list[str]",
                      quality_criteria="Todas las tablas con esquema completo."),
            FieldSpec("lineage.downstream_impact", True, "PARCIAL",
                      quality_criteria="Que pasa si una tabla base cambia y a quien notificar.",
                      user_help="¿Qué reportes o análisis dependen de esta vista? A quién le importa si cambia."),
            FieldSpec("lineage.downstream_tables", False, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Vistas o modelos que consumen esta vista.",
                      user_help="Otras vistas o reportes que usan ésta como fuente."),
        )),
        SectionSpec("governance", "Gobernanza", (
            FieldSpec("governance.technical_owner", True, "HUMANO",
                      quality_criteria="Email o alias.",
                      user_help="Responsable técnico. La persona/equipo a contactar si algo falla."),
            FieldSpec("governance.business_owner", True, "HUMANO",
                      quality_criteria="Email o alias. No puede ser igual a technical_owner.",
                      user_help="Responsable de negocio. El dueño de los datos y su uso."),
            FieldSpec("governance.object_status", True, "HUMANO",
                      enum_key="object_status",
                      quality_criteria="Estado actual del objeto.",
                      user_help="¿En qué estado está? Active=en uso, Deprecated=dejar de usar."),
            FieldSpec("governance.doc_last_updated", True, "AUTO",
                      auto_source="Plataforma automatica",
                      quality_criteria="Observacion si supera 90 dias."),
        )),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # STORED PROCEDURE
    # ═══════════════════════════════════════════════════════════════════════
    "stored_procedure": (
        SectionSpec("identification", "Identificacion y Contexto", (
            FieldSpec("identification.physical_name", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.ROUTINES",
                      quality_criteria="Nombre exacto."),
            FieldSpec("identification.business_name", True, "PARCIAL",
                      quality_criteria="Comprensible para un usuario de negocio.",
                      user_help="Nombre amigable del procedimiento que entienda una persona de negocio."),
            FieldSpec("identification.schema_database", True, "AUTO",
                      auto_source="INFORMATION_SCHEMA.ROUTINES",
                      quality_criteria="Formato: {ambiente}.{schema}.{sp}."),
            FieldSpec("identification.object_type", True, "AUTO",
                      quality_criteria="Siempre 'stored_procedure'."),
            FieldSpec("identification.subtype", True, "PARCIAL",
                      enum_key="sp_subtype",
                      quality_criteria="Inferir del nombre y cuerpo del SP.",
                      user_help="Tipo de procedimiento: ETL=carga datos, Calculation=cálculos, Maintenance=limpieza/mantenimiento."),
            FieldSpec("identification.business_domain", True, "HUMANO",
                      quality_criteria="Area funcional responsable.",
                      user_help="¿Qué área de negocio es responsable de este procedimiento?"),
            FieldSpec("identification.sensitivity", True, "PARCIAL",
                      enum_key="sensitivity",
                      quality_criteria="IA sugiere por las tablas que modifica. El humano decide.",
                      user_help="¿Qué tan sensible es? ¿Trabaja con datos confidenciales o personas?"),
        )),
        SectionSpec("description", "Descripcion Funcional", (
            FieldSpec("description.business_description", True, "PARCIAL",
                      min_words=30,
                      quality_criteria="Que hace en terminos de negocio, en que contexto y que produce. No describir el codigo.",
                      user_help="¿Qué hace este procedimiento? Explica el objetivo de negocio, no cómo funciona técnicamente."),
            FieldSpec("sp_interface.transformation_logic", True, "PARCIAL",
                      min_words=15,
                      quality_criteria="Reglas de negocio paso a paso. No el SQL. El humano valida la semantica.",
                      user_help="Paso a paso: qué cambios hace, en qué orden, y qué reglas de negocio aplica."),
            FieldSpec("sp_interface.side_effects", True, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Toda modificacion adicional: tablas, emails, servicios externos.",
                      user_help="Efectos secundarios: ¿Envía emails? ¿Modifica otras tablas? ¿Llama servicios externos?"),
            FieldSpec("sp_interface.is_idempotent", True, "PARCIAL",
                      field_type="boolean",
                      quality_criteria="IA detecta patrones DELETE+INSERT. El humano confirma."),
            FieldSpec("sp_interface.idempotency_explanation", False, "PARCIAL",
                      field_type="string | null",
                      quality_criteria="Explicacion de por que es o no es idempotente."),
        )),
        SectionSpec("sp_interface", "Interfaz Tecnica", (
            FieldSpec("sp_interface.input_parameters", True, "AUTO",
                      is_array=True, item_fields=_PARAM_ITEMS,
                      auto_source="INFORMATION_SCHEMA.PARAMETERS",
                      quality_criteria="Nombre, tipo, required, default. Descripciones son borrador a validar."),
            FieldSpec("sp_interface.return_values", True, "PARCIAL",
                      field_type="string | null",
                      quality_criteria="Documentar codigos de resultado y su semantica."),
            FieldSpec("sp_interface.tables_read", True, "AUTO",
                      auto_source="sys.sql_dependencies / analisis del cuerpo",
                      field_type="list[str]",
                      quality_criteria="Todas las tablas de las que el SP lee."),
            FieldSpec("sp_interface.tables_modified", True, "AUTO",
                      auto_source="Analisis del cuerpo (INSERT/UPDATE/DELETE)",
                      field_type="list[str]",
                      quality_criteria="Todas las tablas que el SP modifica, con tipo de operacion."),
            FieldSpec("sp_interface.external_dependencies", False, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Llamadas a otros SPs/funciones. El humano agrega servicios externos."),
            FieldSpec("sp_interface.expected_execution_time", True, "HUMANO",
                      quality_criteria="Rango en condiciones normales.",
                      user_help="¿Cuánto tarda en ejecutarse? (minutos, segundos) en condiciones normales."),
            FieldSpec("sp_interface.error_handling", True, "PARCIAL",
                      quality_criteria="IA detecta bloques TRY/CATCH. El humano valida politica de errores."),
        )),
        SectionSpec("execution", "Ejecucion y Gobernanza", (
            FieldSpec("sp_interface.execution_example", True, "PARCIAL",
                      quality_criteria="Debe ser copiable y ejecutable con valores reales."),
            FieldSpec("sp_interface.who_can_execute", True, "PARCIAL",
                      quality_criteria="El humano define la politica intencional."),
            FieldSpec("sp_interface.when_to_execute", True, "HUMANO",
                      quality_criteria="Contexto, scheduler y restricciones operacionales.",
                      user_help="¿Cuándo ejecutar? Contexto, horario, frecuencia, y restricciones (no en horario pico, etc)."),
            FieldSpec("sp_interface.preconditions", True, "HUMANO",
                      field_type="list[str]",
                      quality_criteria="Que debe estar listo antes de ejecutar.",
                      user_help="Condiciones previas: ¿Qué debe completarse antes? ¿Qué datos deben estar listos?"),
            FieldSpec("governance.technical_owner", True, "HUMANO",
                      quality_criteria="Email o alias.",
                      user_help="Responsable técnico. La persona a contactar si algo falla."),
            FieldSpec("governance.business_owner", True, "HUMANO",
                      quality_criteria="Email o alias. No puede ser igual a technical_owner.",
                      user_help="Responsable de negocio. Quién pidió esto y depende de que funcione."),
            FieldSpec("governance.object_status", True, "HUMANO",
                      enum_key="object_status",
                      quality_criteria="Estado actual del objeto.",
                      user_help="¿En qué estado está? Active=producción, Deprecated=descontinuado, Experimental=pruebas."),
            FieldSpec("governance.doc_last_updated", True, "AUTO",
                      auto_source="Plataforma automatica",
                      quality_criteria="Observacion si supera 90 dias."),
        )),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════
    "dashboard": (
        SectionSpec("identification", "Identificacion y Contexto", (
            FieldSpec("identification.physical_name", True, "PARCIAL",
                      auto_source="Tableau MCP extrae nombre",
                      quality_criteria="El humano confirma.",
                      user_help="Nombre técnico del dashboard (tal cual está en Tableau)."),
            FieldSpec("identification.business_name", True, "PARCIAL",
                      quality_criteria="Comprensible para usuario de negocio.",
                      user_help="Nombre amigable: ¿Cómo se llama en el día a día?"),
            FieldSpec("identification.object_type", True, "AUTO",
                      quality_criteria="Siempre 'dashboard'."),
            FieldSpec("identification.business_domain", True, "HUMANO",
                      quality_criteria="Area funcional de negocio.",
                      user_help="¿Qué área de negocio lo usa? Ventas, Finanzas, Marketing, etc."),
            FieldSpec("identification.sensitivity", True, "HUMANO",
                      enum_key="sensitivity",
                      quality_criteria="Solo el humano conoce la politica de acceso real.",
                      user_help="¿Qué tan sensible? ¿Públicos los números o solo para directivos?"),
            FieldSpec("dashboard.bi_tool", True, "AUTO",
                      auto_source="Contexto de conexion Tableau MCP",
                      quality_criteria="Nombre + URL de la plataforma."),
            FieldSpec("dashboard.url", True, "AUTO",
                      auto_source="Tableau MCP",
                      quality_criteria="URL directa al dashboard."),
            FieldSpec("dashboard.dashboard_type", True, "HUMANO",
                      enum_key="dashboard_type",
                      quality_criteria="Tipo de dashboard.",
                      user_help="Tipo: Strategic=decisiones altas, Tactical=operativo diario, Operational=monitoreo real-time."),
        )),
        SectionSpec("description", "Descripcion y Audiencia", (
            FieldSpec("description.purpose", True, "PARCIAL",
                      min_words=25,
                      quality_criteria="Que decision soporta, quien lo usa, con que frecuencia.",
                      user_help="¿Para qué sirve? ¿Qué decisiones de negocio soporta? ¿Quién lo usa?"),
            FieldSpec("description.audience", True, "HUMANO",
                      field_type="list[str]",
                      quality_criteria="Roles especificos, no departamentos generales.",
                      user_help="¿Quién lo usa? Roles específicos (CFO, Gerentes de Ventas, Analistas)."),
            FieldSpec("dashboard.usage_frequency", True, "HUMANO",
                      quality_criteria="Con que frecuencia y en que contexto se consulta.",
                      user_help="¿Cada cuándo se consulta? ¿Diariamente, semanalmente? ¿Antes de reuniones?"),
            FieldSpec("description.questions_answered", True, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="3 a 5 preguntas concretas de negocio. El humano valida.",
                      user_help="3-5 preguntas que responde: ¿Cuáles son mis Top 5 clientes? ¿Cómo va el trimestre?"),
        )),
        SectionSpec("metrics", "Metricas y Definiciones", (
            FieldSpec("dashboard.metrics", True, "PARCIAL",
                      is_array=True, item_fields=_METRIC_ITEMS,
                      auto_source="Tableau MCP extrae nombre y fuente",
                      quality_criteria="Ninguna metrica sin definicion. Incluir: nombre, definicion, formula, fuente, periodicidad, filtros."),
            FieldSpec("dashboard.north_star_metric", True, "HUMANO",
                      quality_criteria="Solo el humano puede definir cual es el indicador central.",
                      user_help="La métrica más importante del dashboard. La que más importa ver de un vistazo."),
            FieldSpec("dashboard.available_filters", True, "PARCIAL",
                      field_type="list[str]",
                      auto_source="Tableau MCP extrae filtros disponibles",
                      quality_criteria="El humano valida los valores por defecto intencionales."),
            FieldSpec("dashboard.implicit_filters", True, "PARCIAL",
                      field_type="list[str]",
                      quality_criteria="Filtros siempre activos e invisibles al usuario."),
            FieldSpec("dashboard.color_logic", False, "PARCIAL",
                      field_type="string | null",
                      quality_criteria="El humano documenta si los umbrales no estan en los datos."),
        )),
        SectionSpec("sources", "Fuentes y Actualizacion", (
            FieldSpec("lineage.data_sources", True, "AUTO",
                      auto_source="Tableau MCP",
                      field_type="list[str]",
                      quality_criteria="Todas las tablas/vistas con esquema completo."),
            FieldSpec("lineage.refresh_frequency", True, "HUMANO",
                      quality_criteria="Frecuencia + horario + timezone."),
            FieldSpec("lineage.data_latency", True, "HUMANO",
                      quality_criteria="Tiempo maximo entre evento real y reflejo en el dashboard."),
            FieldSpec("dashboard.no_data_interpretation", True, "HUMANO",
                      quality_criteria="Que significa null, 0 o vacio."),
            FieldSpec("governance.technical_owner", True, "HUMANO",
                      quality_criteria="Email o alias."),
            FieldSpec("governance.business_owner", True, "HUMANO",
                      quality_criteria="Email o alias. No puede ser igual a technical_owner."),
            FieldSpec("governance.object_status", True, "HUMANO",
                      enum_key="object_status",
                      quality_criteria="Estado actual del objeto."),
            FieldSpec("governance.doc_last_updated", True, "AUTO",
                      auto_source="Plataforma automatica",
                      quality_criteria="Observacion si supera 90 dias."),
        )),
    ),
}


# ── Funciones de acceso ──────────────────────────────────────────────────────

def get_spec(object_type: str) -> tuple[SectionSpec, ...]:
    """Retorna las secciones completas para un tipo de objeto."""
    if object_type not in _SPECS:
        raise ValueError(f"Tipo '{object_type}' no soportado. Validos: {list(_SPECS.keys())}")
    return _SPECS[object_type]


def get_all_fields(object_type: str) -> list[FieldSpec]:
    """Retorna todos los campos (flattened) de un tipo de objeto."""
    return [f for s in get_spec(object_type) for f in s.fields]


def get_required_fields(object_type: str) -> list[FieldSpec]:
    """Solo campos REQ."""
    return [f for f in get_all_fields(object_type) if f.required]


def get_fields_by_completion(object_type: str, completion: str) -> list[FieldSpec]:
    """Campos filtrados por tipo de completado (AUTO, PARCIAL, HUMANO)."""
    return [f for f in get_all_fields(object_type) if f.completion == completion]


def get_section_labels(object_type: str) -> dict[str, str]:
    """Mapeo section_key -> label para el frontend."""
    return {s.key: s.label for s in get_spec(object_type)}


def get_enum_values(enum_key: str) -> list[str]:
    """Valores validos para un campo enum."""
    return VALID_ENUMS.get(enum_key, [])


def supported_types() -> list[str]:
    """Lista de tipos de objeto soportados."""
    return list(_SPECS.keys())


# ── Generacion de JSON schema ────────────────────────────────────────────────

def _item_fields_to_schema(items: tuple[ItemField, ...]) -> dict:
    """Convierte ItemFields a un JSON schema de objeto."""
    props = {}
    for item in items:
        if item.type == "boolean":
            props[item.name] = {"type": "boolean"}
        elif item.type == "list[str]":
            props[item.name] = {"type": "array", "items": {"type": "string"}}
        elif "null" in item.type:
            props[item.name] = {"type": ["string", "null"]}
        else:
            props[item.name] = {"type": "string"}
    return {
        "type": "object",
        "properties": props,
        "required": [i.name for i in items],
    }


def get_json_schema(object_type: str) -> dict:
    """
    Genera el JSON schema completo para un tipo de objeto.
    Se usa como referencia para el agente generador.
    """
    sections: dict[str, dict] = {}

    for field_spec in get_all_fields(object_type):
        section_key, field_name = field_spec.path.split(".", 1)

        if section_key not in sections:
            sections[section_key] = {}

        if field_spec.is_array and field_spec.item_fields:
            sections[section_key][field_name] = {
                "type": "array",
                "items": _item_fields_to_schema(field_spec.item_fields),
            }
        elif field_spec.field_type == "boolean":
            sections[section_key][field_name] = {"type": "boolean"}
        elif field_spec.field_type == "list[str]":
            sections[section_key][field_name] = {
                "type": "array",
                "items": {"type": "string"},
            }
        elif "null" in field_spec.field_type:
            sections[section_key][field_name] = {"type": ["string", "null"]}
        else:
            sections[section_key][field_name] = {"type": "string"}

    schema: dict = {}
    for sec_key, props in sections.items():
        schema[sec_key] = {
            "type": "object",
            "properties": props,
        }

    return schema


def get_json_schema_str(object_type: str) -> str:
    """Version string del JSON schema para incrustar en prompts."""
    return json.dumps(get_json_schema(object_type), indent=2, ensure_ascii=False)


# ── Generacion de instrucciones para prompts ─────────────────────────────────

def build_generator_instructions(object_type: str) -> str:
    """
    Genera las instrucciones campo-por-campo para el prompt del generador.
    Se construye dinamicamente desde el spec — si se agrega un campo, las
    instrucciones se actualizan solas.
    """
    auto_lines = []
    parcial_lines = []
    humano_lines = []

    for f in get_all_fields(object_type):
        label = f.path
        criteria = f.quality_criteria

        if f.enum_key:
            values = ", ".join(VALID_ENUMS[f.enum_key])
            criteria += f" Valores validos: {values}."

        if f.min_words:
            criteria += f" Minimo {f.min_words} palabras."

        if f.must_not_contain:
            forbidden = "; ".join(f'"{x}"' for x in f.must_not_contain)
            criteria += f" NO usar: {forbidden}."

        line = f"  - `{label}`: {criteria}"

        if f.completion == "AUTO":
            src = f" (fuente: {f.auto_source})" if f.auto_source else ""
            auto_lines.append(f"  - `{label}`{src}: {criteria}")
        elif f.completion == "PARCIAL":
            parcial_lines.append(line)
        else:
            humano_lines.append(line)

    parts = []

    if auto_lines:
        parts.append("Campos AUTO — usa los datos del metadata provisto:\n" + "\n".join(auto_lines))

    if parcial_lines:
        parts.append("Campos PARCIAL — genera un borrador que cumpla estos criterios:\n" + "\n".join(parcial_lines))

    if humano_lines:
        parts.append(
            'Campos HUMANO — usa "[REQUIERE REVISION HUMANA]" como valor:\n' + "\n".join(humano_lines)
        )

    return "\n\n".join(parts)


def build_auditor_criteria(object_type: str) -> str:
    """
    Genera los criterios de validacion para el prompt del auditor.
    Solo incluye campos HUMANO y PARCIAL requeridos — los AUTO los completa
    el sistema y el usuario no puede editarlos, por lo que no deben auditarse.
    """
    lines = []
    for f in get_required_fields(object_type):
        if f.completion == "AUTO":
            continue  # el sistema los genera; el usuario no puede corregirlos
        detail = f.quality_criteria
        if f.enum_key:
            values = ", ".join(VALID_ENUMS[f.enum_key])
            detail += f" Valores validos: {values}."
        if f.min_words:
            detail += f" Minimo {f.min_words} palabras."
        if f.must_not_contain:
            forbidden = "; ".join(f'"{x}"' for x in f.must_not_contain)
            detail += f" Rechazar si contiene: {forbidden}."

        lines.append(f"  - `{f.path}` ({f.completion}): {detail}")

    return "Criterios de validación por campo:\n" + "\n".join(lines)


# ── Export para el endpoint /api/spec ────────────────────────────────────────

def spec_to_dict(object_type: str) -> dict:
    """Serializa el spec completo para exponerlo al frontend via API."""
    sections = []
    for s in get_spec(object_type):
        fields = []
        for f in s.fields:
            fd: dict = {
                "path": f.path,
                "required": f.required,
                "completion": f.completion,
                "quality_criteria": f.quality_criteria,
                "user_help": f.user_help,
                "field_type": f.field_type,
                "is_array": f.is_array,
            }
            if f.enum_key:
                fd["valid_values"] = VALID_ENUMS[f.enum_key]
            if f.min_words:
                fd["min_words"] = f.min_words
            if f.item_fields:
                fd["item_fields"] = [{"name": i.name, "type": i.type} for i in f.item_fields]
            fields.append(fd)
        sections.append({
            "key": s.key,
            "label": s.label,
            "fields": fields,
        })
    return {
        "object_type": object_type,
        "sections": sections,
        "enums": VALID_ENUMS,
    }
