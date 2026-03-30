"use client";

import { useDocSpec } from "@/lib/hooks";
import type { Document, DocSpec, FieldDef } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

export function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function esc(v: unknown): string {
  if (v == null) return "—";
  return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

// ── Array card renderer (for wide arrays with > 4 item_fields) ────────────────

function renderArrayAsCards(rows: Record<string, unknown>[]): string {
  const parts = rows.map((row) => {
    const name   = esc(row["physical_name"] ?? row["name"] ?? "");
    const type   = esc(row["data_type"] ?? row["type"] ?? "");
    const desc   = esc(row["description"] ?? row["definition"] ?? "");

    const badges = [
      row["is_pk"]         ? "<span class='arr-badge arr-badge-pk'>PK</span>"    : "",
      row["is_fk"]         ? "<span class='arr-badge arr-badge-fk'>FK</span>"    : "",
      row["is_calculated"] ? "<span class='arr-badge arr-badge-calc'>CALC</span>": "",
      row["nullable"] === false ? "<span class='arr-badge arr-badge-req'>NOT NULL</span>" : "",
      row["required"] === true  ? "<span class='arr-badge arr-badge-req'>REQ</span>"      : "",
    ].join("");

    const extras: string[] = [];
    const bizName = row["business_name"];
    if (bizName && bizName !== row["physical_name"] && bizName !== row["name"])
      extras.push(`Nombre negocio: ${esc(bizName)}`);
    if (row["fk_reference"])  extras.push(`→ ${esc(row["fk_reference"])}`);
    if (row["formula"])       extras.push(`fórmula: ${esc(row["formula"])}`);
    if (row["value_domain"] ?? row["valid_domain"])
      extras.push(`valores: ${esc(row["value_domain"] ?? row["valid_domain"])}`);
    if (row["default_value"] != null) extras.push(`default: ${esc(row["default_value"])}`);
    if (row["source"])        extras.push(`fuente: ${esc(row["source"])}`);
    if (row["periodicity"])   extras.push(`periodicidad: ${esc(row["periodicity"])}`);

    const extrasHtml = extras.map((e) => `<div class='arr-row-extra'>${e}</div>`).join("");
    const typeHtml   = type ? `<span class='field-type'>${type}</span>` : "";
    const descHtml   = desc ? `<div class='arr-row-desc'>${desc}</div>` : "";

    return `<div class='arr-row'>
      <div class='arr-row-header'>
        <span class='field-name'>${name}</span>${typeHtml}${badges}
      </div>${descHtml}${extrasHtml}
    </div>`;
  });

  return `<div class='arr-list' style='margin-left:28px'>${parts.join("")}</div>`;
}

// ── Field renderers ───────────────────────────────────────────────────────────

function renderFieldValue(value: unknown, fieldDef: FieldDef): string {
  // Human-review placeholder
  if (typeof value === "string" && value.startsWith("[REQUIERE")) {
    return `<div class='placeholder-value'>${esc(value)}</div>`;
  }

  if (value == null || value === "") return "";

  // Array of objects
  if (fieldDef.is_array && fieldDef.item_fields?.length) {
    if (!Array.isArray(value) || !value.length) return "";
    const rows = value as Record<string, unknown>[];

    // Wide arrays (> 4 columns) → card list to avoid horizontal overflow
    if (fieldDef.item_fields.length > 4) {
      return renderArrayAsCards(rows);
    }

    // Narrow arrays (≤ 4 columns) → standard table
    const headers = fieldDef.item_fields
      .map((f) => `<th>${esc(humanize(f.name))}</th>`)
      .join("");
    const tableRows = rows
      .map((row) => {
        const cells = fieldDef.item_fields!.map((f) => {
          const v = row[f.name];
          if (f.name === "physical_name" || f.name === "name" || f.name === "business_name") {
            return `<td><span class='field-name'>${esc(v)}</span></td>`;
          }
          if (f.name === "data_type" || f.name === "type") {
            return `<td><span class='field-type'>${esc(v)}</span></td>`;
          }
          if (f.type === "boolean") {
            return `<td class='${v ? "nullable-no" : "nullable-yes"}'>${v ? "Sí" : "No"}</td>`;
          }
          return `<td style='color:#4a4a6a;font-size:12px;line-height:1.5'>${esc(v)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");
    return `<div style='overflow-x:auto;margin-left:28px'>
      <table class='fields-table'>
        <thead><tr>${headers}</tr></thead>
        <tbody>${tableRows}</tbody>
      </table></div>`;
  }

  // String array → tag list
  if (fieldDef.field_type === "list[str]") {
    if (!Array.isArray(value) || !value.length) return "";
    return `<div class='tag-list'>${(value as string[]).map((i) => `<span class='tag'>${esc(i)}</span>`).join("")}</div>`;
  }

  // Boolean
  if (fieldDef.field_type === "boolean") {
    return `<div class='section-body'>${value ? "Sí" : "No"}</div>`;
  }

  // String (possibly multiline)
  const str = String(value);
  if (str.length > 200 && str.includes("\n")) {
    return `<pre class='code-block'>${esc(str)}</pre>`;
  }
  return `<div class='section-body'>${esc(str)}</div>`;
}

// ── HTML builder ──────────────────────────────────────────────────────────────

export function buildDocHtml(doc: Document, spec: DocSpec): string {
  const c = doc.content as Record<string, unknown>;
  const get = (path: string) => getNestedValue(c, path);

  const name = esc(get("identification.physical_name") || get("identification.business_name") || doc.name);
  const domain = esc(get("identification.business_domain") || "");
  const owner = esc(get("governance.technical_owner") || "");
  const updated = esc(String(get("governance.doc_last_updated") || "").slice(0, 10) || "—");

  const statusMap: Record<string, [string, string]> = {
    approved: ["approved", "Aprobado"],
    draft:    ["draft",    "Borrador"],
    rejected: ["rejected", "Rechazado"],
  };
  const [statusCls, statusLabel] = statusMap[doc.status] ?? ["draft", doc.status];
  const typeLabel = doc.object_type.replace(/_/g, " ").toUpperCase();

  let sectionsHtml = "";
  let num = 1;

  for (const section of spec.sections) {
    let sectionBody = "";

    for (const fieldDef of section.fields) {
      const fieldName = fieldDef.path.split(".").pop() ?? fieldDef.path;
      const value = getNestedValue(c, fieldDef.path);
      const rendered = renderFieldValue(value, fieldDef);
      if (!rendered) continue;

      const badge =
        fieldDef.completion === "HUMANO"
          ? "<span class='completion-badge humano'>H</span>"
          : fieldDef.completion === "PARCIAL"
          ? "<span class='completion-badge parcial'>P</span>"
          : "";

      const helpIcon =
        (fieldDef.completion === "HUMANO" || fieldDef.completion === "PARCIAL") && fieldDef.user_help
          ? `<span class='help-icon' title='${esc(fieldDef.user_help)}'>?</span>`
          : "";

      sectionBody += `<div class='field-entry'>
        <div class='field-label'>${esc(humanize(fieldName))}${badge}${helpIcon}</div>
        ${rendered}
      </div>`;
    }

    if (!sectionBody) continue;

    sectionsHtml += `<div class='section'>
      <div class='section-heading'>
        <span class='section-num'>${String(num).padStart(2, "0")}</span>
        <span class='section-title'>${esc(section.label)}</span>
        <div class='section-line'></div>
      </div>
      ${sectionBody}
    </div>`;
    num++;
  }

  if (!sectionsHtml) {
    sectionsHtml = `<p style='color:#9090b0;font-size:13px;padding:16px 0'>No hay contenido generado aún.</p>`;
  }

  return `
<div class='doc-page' style='padding:40px 48px;max-width:100%'>
  <div class='doc-eyebrow'>
    <span class='doc-type-pill'>${esc(typeLabel)}</span>
    <span class='doc-domain'>${domain}</span>
    <span style='flex:1'></span>
    <span class='status-badge ${statusCls}'><span class='status-dot'></span>${statusLabel}</span>
  </div>
  <h1 class='doc-title'>${name}</h1>
  <hr class='doc-rule' style='margin:16px 0 20px'>
  <div class='doc-meta-bar'>
    <div class='meta-item'><div class='meta-label'>Dominio</div><div class='meta-value' title='${domain}'>${domain || "—"}</div></div>
    <div class='meta-item'><div class='meta-label'>Owner técnico</div><div class='meta-value' title='${owner}'>${owner || "—"}</div></div>
    <div class='meta-item'><div class='meta-label'>Última actualización</div><div class='meta-value'>${updated}</div></div>
  </div>
  ${sectionsHtml}
  <div class='doc-footer'>
    <div class='doc-footer-left'>Generado por memorIA · Creado por ${esc(doc.created_by)}<br>Este documento es la fuente oficial de verdad para este objeto.</div>
    <div class='doc-footer-right'>${name}</div>
  </div>
</div>`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DocViewer({ doc }: { doc: Document }) {
  const spec = useDocSpec(doc.object_type);

  if (!spec) {
    return (
      <div className="h-full overflow-y-auto flex items-center justify-center">
        <span className="text-sm text-[#9090b0]">Cargando…</span>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto"
      dangerouslySetInnerHTML={{ __html: buildDocHtml(doc, spec) }}
    />
  );
}
