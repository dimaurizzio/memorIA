"""
Generación de PDFs a partir de documentos v2.
Replica la lógica de renderizado de doc-viewer.tsx en Python
y convierte el HTML resultante a PDF con Playwright.
"""
import html
from typing import Any
from config.doc_spec import spec_to_dict


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(v: Any) -> str:
    if v is None:
        return "—"
    return html.escape(str(v))


def _get(obj: dict, path: str) -> Any:
    parts = path.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _humanize(key: str) -> str:
    return " ".join(word.capitalize() for word in key.split("_"))


# ── Array card renderer (evita tablas anchas) ─────────────────────────────────

def _render_array_as_cards(rows: list, item_fields: list) -> str:
    """
    Renders an array of objects as a definition-list style layout.
    Used when item_fields > 4 to avoid tables that overflow A4 width.
    """
    name_field  = next((f["name"] for f in item_fields if f["name"] in ("physical_name", "name")), None)
    type_field  = next((f["name"] for f in item_fields if f["name"] in ("data_type", "type")), None)
    desc_field  = next((f["name"] for f in item_fields if f["name"] in ("description", "definition")), None)

    parts = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        name_val = _esc(row.get(name_field, "") if name_field else "")
        type_val = _esc(row.get(type_field, "") if type_field else "")
        desc_val = _esc(row.get(desc_field, "") if desc_field else "")

        # Badges for boolean flags
        badges = ""
        if row.get("is_pk"):
            badges += "<span class='badge badge-pk'>PK</span>"
        if row.get("is_fk"):
            badges += "<span class='badge badge-fk'>FK</span>"
        if row.get("is_calculated"):
            badges += "<span class='badge badge-calc'>CALC</span>"
        if row.get("nullable") is False:
            badges += "<span class='badge badge-req'>NOT NULL</span>"
        if row.get("required") is True:
            badges += "<span class='badge badge-req'>REQ</span>"

        # Extra details below description
        extras = []
        biz_name = row.get("business_name")
        if biz_name and biz_name != (row.get(name_field) if name_field else ""):
            extras.append(f"Nombre negocio: {_esc(biz_name)}")
        fk_ref = row.get("fk_reference")
        if fk_ref:
            extras.append(f"→ {_esc(fk_ref)}")
        formula = row.get("formula")
        if formula:
            extras.append(f"fórmula: {_esc(formula)}")
        value_domain = row.get("value_domain") or row.get("valid_domain")
        if value_domain:
            extras.append(f"valores: {_esc(value_domain)}")
        default_val = row.get("default_value")
        if default_val is not None:
            extras.append(f"default: {_esc(default_val)}")
        source = row.get("source")
        if source:
            extras.append(f"fuente: {_esc(source)}")
        periodicity = row.get("periodicity")
        if periodicity:
            extras.append(f"periodicidad: {_esc(periodicity)}")

        extras_html = "".join(f"<div class='field-extra'>{e}</div>" for e in extras)
        type_html = f"<span class='field-type'>{type_val}</span>" if type_val else ""
        desc_html = f"<div class='field-row-desc'>{desc_val}</div>" if desc_val else ""

        parts.append(f"""<div class='field-row'>
  <div class='field-row-header'>
    <span class='field-name'>{name_val}</span>
    {type_html}
    {badges}
  </div>
  {desc_html}
  {extras_html}
</div>""")

    return f"<div class='fields-list'>{''.join(parts)}</div>"


# ── Field renderers ───────────────────────────────────────────────────────────

def _render_field_value(value: Any, field: dict) -> str:
    if isinstance(value, str) and value.startswith("[REQUIERE"):
        return f"<div class='placeholder-value'>{_esc(value)}</div>"

    if value is None or value == "":
        return ""

    # Array de objetos
    if field.get("is_array") and field.get("item_fields"):
        if not isinstance(value, list) or not value:
            return ""
        item_fields = field["item_fields"]

        # Tablas con muchas columnas → card layout para evitar desbordamiento
        if len(item_fields) > 4:
            return _render_array_as_cards(value, item_fields)

        # Tablas pequeñas (≤4 columnas) → tabla normal
        headers = "".join(f"<th>{_esc(_humanize(f['name']))}</th>" for f in item_fields)
        rows = ""
        for row in value:
            if not isinstance(row, dict):
                continue
            cells = ""
            for f in item_fields:
                v = row.get(f["name"])
                name = f["name"]
                ftype = f["type"]
                if name in ("physical_name", "name", "business_name"):
                    cells += f"<td><span class='field-name'>{_esc(v)}</span></td>"
                elif name in ("data_type", "type"):
                    cells += f"<td><span class='field-type'>{_esc(v)}</span></td>"
                elif ftype == "boolean":
                    cls = "nullable-no" if v else "nullable-yes"
                    cells += f"<td class='{cls}'>{'Sí' if v else 'No'}</td>"
                else:
                    cells += f"<td>{_esc(v)}</td>"
            rows += f"<tr>{cells}</tr>"
        return f"""<table class='fields-table'>
        <thead><tr>{headers}</tr></thead>
        <tbody>{rows}</tbody>
      </table>"""

    # Lista de strings → tags
    if field.get("field_type") == "list[str]":
        if not isinstance(value, list) or not value:
            return ""
        tags = "".join(f"<span class='tag'>{_esc(i)}</span>" for i in value)
        return f"<div class='tag-list'>{tags}</div>"

    # Booleano
    if field.get("field_type") == "boolean":
        return f"<div class='section-body'>{'Sí' if value else 'No'}</div>"

    # String
    s = str(value)
    if len(s) > 200 and "\n" in s:
        return f"<pre class='code-block'>{_esc(s)}</pre>"
    return f"<div class='section-body'>{_esc(s)}</div>"


# ── CSS ────────────────────────────────────────────────────────────────────────

_DOC_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&family=Lora:wght@600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: white; font-size: 11px; }

:root {
  --doc-ink: #1a1a2e; --doc-ink-light: #4a4a6a; --doc-ink-faint: #9090b0;
  --doc-accent: #2563b0; --doc-accent-light: #dbeafe;
  --doc-rule: #d4d4c8; --doc-table-header: #f0f0ea; --doc-code-bg: #f4f4f0;
}

.doc-page {
  font-family: 'DM Sans', system-ui, sans-serif;
  background: white;
  color: var(--doc-ink);
}

/* ── Header ── */
.doc-eyebrow { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.doc-type-pill {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 500;
  letter-spacing: 1px; text-transform: uppercase;
  color: var(--doc-accent); background: var(--doc-accent-light);
  padding: 2px 7px; border-radius: 3px;
}
.doc-domain { font-size: 11px; color: var(--doc-ink-faint); }
.doc-title {
  font-family: 'Lora', serif; font-size: 20px; font-weight: 700;
  color: var(--doc-ink); line-height: 1.2; letter-spacing: -0.3px; margin-bottom: 6px;
}
.doc-rule { border: none; border-top: 1px solid var(--doc-rule); margin: 12px 0; }

/* ── Meta bar ── */
.doc-meta-bar {
  display: grid; grid-template-columns: repeat(3, 1fr);
  border: 1px solid var(--doc-rule); border-radius: 4px; overflow: hidden; margin-bottom: 20px;
}
.meta-item { padding: 7px 11px; border-right: 1px solid var(--doc-rule); }
.meta-item:last-child { border-right: none; }
.meta-label { font-size: 8px; font-weight: 600; letter-spacing: .8px; text-transform: uppercase; color: var(--doc-ink-faint); margin-bottom: 2px; }
.meta-value { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 500; color: var(--doc-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Status badge ── */
.status-badge {
  display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 20px;
  font-size: 9px; font-weight: 600; letter-spacing: .5px; text-transform: uppercase;
}
.status-badge.approved { background: #dcfce7; color: #15803d; }
.status-badge.draft    { background: #fef3c7; color: #92400e; }
.status-badge.rejected { background: #fee2e2; color: #991b1b; }
.status-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

/* ── Sections ── */
.section { margin-bottom: 18px; }
.section-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; break-after: avoid; }
.section-num { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--doc-ink-faint); min-width: 16px; }
.section-title { font-family: 'Lora', serif; font-size: 12px; font-weight: 600; color: var(--doc-ink); }
.section-line { flex: 1; height: 1px; background: var(--doc-rule); }
.section-body { font-size: 11px; line-height: 1.65; color: var(--doc-ink-light); padding-left: 22px; }

/* ── Field entries ── */
.field-entry { margin-bottom: 10px; }
.field-label { font-size: 8px; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: var(--doc-ink-faint); padding-left: 22px; margin-bottom: 4px; }
.placeholder-value { font-style: italic; font-size: 11px; color: var(--doc-ink-faint); background: #fef9e7; border-left: 2px solid #fbbf24; padding: 3px 8px 3px 10px; margin-left: 22px; border-radius: 2px; }

/* ── Tags ── */
.tag-list { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 22px; }
.tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; background: var(--doc-code-bg); color: var(--doc-ink); padding: 2px 7px; border-radius: 3px; border: 1px solid var(--doc-rule); }

/* ── Code block ── */
.code-block { background: var(--doc-code-bg); color: var(--doc-ink); padding: 8px 11px; border-radius: 4px; font-size: 10px; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; margin-left: 22px; border: 1px solid var(--doc-rule); }

/* ── Small tables (≤4 cols) ── */
.fields-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-left: 22px; width: calc(100% - 22px); }
.fields-table thead tr { background: var(--doc-table-header); }
.fields-table th { text-align: left; padding: 5px 9px; font-size: 8px; font-weight: 600; letter-spacing: .8px; text-transform: uppercase; color: var(--doc-ink-faint); border-bottom: 1px solid var(--doc-rule); }
.fields-table td { padding: 5px 9px; border-bottom: 1px solid var(--doc-rule); vertical-align: top; color: var(--doc-ink-light); line-height: 1.4; font-size: 11px; }
.fields-table tr:last-child td { border-bottom: none; }

/* ── Card layout for wide arrays (fields, metrics, params) ── */
.fields-list { margin-left: 22px; }
.field-row { padding: 6px 0; border-bottom: 1px solid var(--doc-rule); break-inside: avoid; }
.field-row:last-child { border-bottom: none; }
.field-row-header { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-bottom: 2px; }
.field-row-desc { font-size: 11px; color: var(--doc-ink-light); line-height: 1.5; margin-top: 1px; }
.field-extra { font-size: 9px; color: var(--doc-ink-faint); margin-top: 2px; font-family: 'JetBrains Mono', monospace; }

/* ── Type atoms ── */
.field-name { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--doc-ink); font-weight: 600; }
.field-type { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--doc-accent); background: var(--doc-accent-light); padding: 1px 5px; border-radius: 3px; }
.nullable-yes { font-size: 10px; color: var(--doc-ink-faint); }
.nullable-no  { font-size: 10px; color: var(--doc-ink); font-weight: 500; }

/* ── Badges (PK, FK, CALC, NOT NULL) ── */
.badge { font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700; padding: 1px 4px; border-radius: 2px; letter-spacing: 0.5px; text-transform: uppercase; }
.badge-pk   { background: #fef3c7; color: #92400e; }
.badge-fk   { background: #dbeafe; color: #1d4ed8; }
.badge-calc { background: #f0f0ea; color: #4a4a6a; }
.badge-req  { background: #fee2e2; color: #991b1b; }

/* ── Footer ── */
.doc-footer { margin-top: 20px; padding-top: 10px; border-top: 1px solid var(--doc-rule); display: flex; justify-content: space-between; align-items: center; }
.doc-footer-left { font-size: 9px; color: var(--doc-ink-faint); line-height: 1.5; }
.doc-footer-right { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--doc-ink-faint); }
"""


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_doc_html(doc: dict) -> str:
    content = doc.get("content", {})
    object_type = doc.get("object_type", "table")
    spec = spec_to_dict(object_type)

    name    = _esc(_get(content, "identification.physical_name") or _get(content, "identification.business_name") or doc.get("name", ""))
    domain  = _esc(_get(content, "identification.business_domain") or "")
    owner   = _esc(_get(content, "governance.technical_owner") or "")
    updated = _esc(str(_get(content, "governance.doc_last_updated") or "—")[:10])

    status = doc.get("status", "draft")
    status_labels = {"approved": "Aprobado", "draft": "Borrador", "rejected": "Rechazado"}
    status_label = status_labels.get(status, status)
    type_label = object_type.replace("_", " ").upper()

    sections_html = ""
    num = 1
    for section in spec["sections"]:
        section_body = ""
        for field in section["fields"]:
            field_name = field["path"].split(".")[-1]
            value = _get(content, field["path"])
            rendered = _render_field_value(value, field)
            if not rendered:
                continue
            section_body += f"""<div class='field-entry'>
        <div class='field-label'>{_esc(_humanize(field_name))}</div>
        {rendered}
      </div>"""

        if not section_body:
            continue

        sections_html += f"""<div class='section'>
      <div class='section-heading'>
        <span class='section-num'>{str(num).zfill(2)}</span>
        <span class='section-title'>{_esc(section['label'])}</span>
        <div class='section-line'></div>
      </div>
      {section_body}
    </div>"""
        num += 1

    created_by = _esc(doc.get("created_by", ""))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{name}</title>
  <style>{_DOC_CSS}</style>
</head>
<body>
  <div class='doc-page'>
    <div class='doc-eyebrow'>
      <span class='doc-type-pill'>{_esc(type_label)}</span>
      <span class='doc-domain'>{domain}</span>
      <span style='flex:1'></span>
      <span class='status-badge {status}'><span class='status-dot'></span>{status_label}</span>
    </div>
    <h1 class='doc-title'>{name}</h1>
    <hr class='doc-rule' style='margin:12px 0 16px'>
    <div class='doc-meta-bar'>
      <div class='meta-item'><div class='meta-label'>Dominio</div><div class='meta-value'>{domain or '—'}</div></div>
      <div class='meta-item'><div class='meta-label'>Owner técnico</div><div class='meta-value'>{owner or '—'}</div></div>
      <div class='meta-item'><div class='meta-label'>Última actualización</div><div class='meta-value'>{updated}</div></div>
    </div>
    {sections_html or "<p style='color:#9090b0;font-size:11px'>No hay contenido generado.</p>"}
    <div class='doc-footer'>
      <div class='doc-footer-left'>Generado por memorIA · Creado por {created_by}<br>Este documento es la fuente oficial de verdad para este objeto.</div>
      <div class='doc-footer-right'>{name}</div>
    </div>
  </div>
</body>
</html>"""


# ── PDF generation ────────────────────────────────────────────────────────────

def generate_pdf(doc: dict) -> bytes:
    from playwright.sync_api import sync_playwright
    html_content = build_doc_html(doc)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            margin={"top": "22mm", "right": "24mm", "bottom": "22mm", "left": "24mm"},
            print_background=True,
        )
        browser.close()
    return pdf_bytes
