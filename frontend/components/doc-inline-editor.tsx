"use client";

import { useState, useEffect } from "react";
import { patchDocument } from "@/lib/api";
import { useDocSpec } from "@/lib/hooks";
import { DocViewer, getNestedValue } from "@/components/doc-viewer";
import type { Document, FieldDef, DocSpec, AuditIssue } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): void {
  const parts = path.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!cur[parts[i]] || typeof cur[parts[i]] !== "object") cur[parts[i]] = {};
    cur = cur[parts[i]] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]] = value;
}

function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

function initFormState(content: Record<string, unknown>, spec: DocSpec): Record<string, unknown> {
  const state: Record<string, unknown> = {};
  for (const section of spec.sections) {
    for (const field of section.fields) {
      if (field.completion === "AUTO") continue;
      const value = getNestedValue(content, field.path);
      if (value != null) state[field.path] = value;
    }
  }
  return state;
}

function buildUpdatedContent(
  base: Record<string, unknown>,
  formState: Record<string, unknown>
): Record<string, unknown> {
  const result = JSON.parse(JSON.stringify(base)) as Record<string, unknown>;
  for (const [path, value] of Object.entries(formState)) {
    setNestedValue(result, path, value);
  }
  return result;
}

// ── Field status ─────────────────────────────────────────────────────────────

type FieldStatus = "ok" | "required" | "review";

function fieldStatus(value: unknown, fieldDef: FieldDef): FieldStatus {
  if (Array.isArray(value)) {
    return value.length === 0 && fieldDef.required ? "required" : "ok";
  }
  if (typeof value === "boolean") return "ok"; // true/false son selecciones válidas
  const str = typeof value === "string" ? value.trim() : "";
  if (str.startsWith("[REQUIERE")) return "review";
  if (str === "" && fieldDef.required) return "required";
  return "ok";
}

function borderCls(s: FieldStatus): string {
  if (s === "required") return "border-red-400 focus:border-red-500";
  if (s === "review") return "border-amber-400 focus:border-amber-500";
  return "border-[#d4d4c8] focus:border-[#2563b0]";
}

// ── Section heading ───────────────────────────────────────────────────────────

function SectionHeading({ num, title }: { num: string; title: string }) {
  return (
    <div className="section-heading">
      <span className="section-num">{num}</span>
      <span className="section-title">{title}</span>
      <div className="section-line" />
    </div>
  );
}

// ── Field editor ──────────────────────────────────────────────────────────────

function FieldEditor({
  fieldDef,
  value,
  onChange,
}: {
  fieldDef: FieldDef;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const status = fieldStatus(value, fieldDef);

  // Array of objects — per-item editor for string subfields
  if (fieldDef.is_array) {
    const items = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
    const allSubFields = fieldDef.item_fields ?? [];
    const identifierKey = allSubFields[0]?.name ?? "name";
    const editableSubFields = allSubFields.filter(
      (f) => f.name !== identifierKey && (f.type === "string" || f.type === "string | null")
    );

    if (items.length === 0) {
      return (
        <p className="text-[11px] text-[#9090b0] italic" style={{ paddingLeft: "28px" }}>
          Sin elementos. Re-generá el documento para cargar los datos.
        </p>
      );
    }

    return (
      <div style={{ paddingLeft: "28px" }} className="space-y-2">
        {items.map((item, idx) => {
          const identifier = String(item[identifierKey] ?? `#${idx + 1}`);
          const dataType = typeof item.data_type === "string" ? item.data_type : null;
          return (
            <div key={idx} className="border border-[#e4e4dc] rounded-lg px-3 py-2.5 bg-[#fafaf8]">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[11px] font-semibold text-[#4a4a6a] font-mono">{identifier}</span>
                {dataType && (
                  <span className="text-[10px] text-[#9090b0] bg-[#f0f0e8] px-1.5 py-0.5 rounded font-mono">
                    {dataType}
                  </span>
                )}
              </div>
              {editableSubFields.length > 0 ? (
                <div className="space-y-1.5">
                  {editableSubFields.map((subField) => {
                    const raw = item[subField.name];
                    const subVal = typeof raw === "string" ? raw : raw == null ? "" : String(raw);
                    const subStatus: FieldStatus = subVal.trim().startsWith("[REQUIERE") ? "review" : "ok";
                    return (
                      <div key={subField.name}>
                        <div className="text-[10px] text-[#9090b0] mb-0.5">{humanize(subField.name)}</div>
                        <textarea
                          value={subVal}
                          onChange={(e) => {
                            const updated = items.map((it, i) =>
                              i === idx ? { ...it, [subField.name]: e.target.value } : it
                            );
                            onChange(updated);
                          }}
                          rows={2}
                          className={`w-full text-[11px] leading-relaxed text-[#4a4a6a] bg-white border rounded px-2 py-1.5 focus:outline-none resize-none ${borderCls(subStatus)}`}
                          style={{ fontFamily: "var(--font-dm-sans,'DM Sans'),system-ui,sans-serif" }}
                        />
                        {subStatus === "review" && (
                          <p className="text-[10px] text-amber-500 mt-0.5">Requiere revisión humana</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[10px] text-[#9090b0] italic">Sin campos editables.</p>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Boolean
  if (fieldDef.field_type === "boolean") {
    const boolStr = value === true ? "true" : value === false ? "false" : "";
    return (
      <div style={{ paddingLeft: "28px" }}>
        <select
          value={boolStr}
          onChange={(e) => {
            const v = e.target.value;
            onChange(v === "true" ? true : v === "false" ? false : null);
          }}
          className="text-xs text-[#4a4a6a] bg-white border border-[#d4d4c8] rounded px-2 py-1 focus:outline-none focus:border-[#2563b0]"
        >
          <option value="">— Sin definir —</option>
          <option value="true">Sí</option>
          <option value="false">No</option>
        </select>
        <StatusHint s={status} />
      </div>
    );
  }

  // String array
  if (fieldDef.field_type === "list[str]") {
    const listStr = Array.isArray(value) ? (value as string[]).join("\n") : String(value ?? "");
    return (
      <div style={{ paddingLeft: "28px" }}>
        <textarea
          value={listStr}
          onChange={(e) => {
            // No trimear mientras el usuario escribe — solo filtrar líneas completamente vacías
            const lines = e.target.value.split("\n").filter(Boolean);
            onChange(lines);
          }}
          placeholder="Un ítem por línea…"
          rows={3}
          className={`w-full text-[11px] leading-relaxed text-[#4a4a6a] bg-white border rounded px-3 py-2 focus:outline-none resize-none ${borderCls(status)}`}
          style={{ fontFamily: "var(--font-dm-sans,'DM Sans'),system-ui,sans-serif" }}
        />
        <StatusHint s={status} />
      </div>
    );
  }

  // Enum dropdown
  if (fieldDef.valid_values?.length) {
    const enumVal = typeof value === "string" && !value.startsWith("[REQUIERE") ? value : "";
    return (
      <div style={{ paddingLeft: "28px" }}>
        <select
          value={enumVal}
          onChange={(e) => onChange(e.target.value)}
          className={`text-xs text-[#4a4a6a] bg-white border rounded px-2 py-1.5 focus:outline-none ${borderCls(status)}`}
          style={{ fontFamily: "var(--font-dm-sans,'DM Sans'),system-ui,sans-serif" }}
        >
          <option value="">— Seleccionar —</option>
          {fieldDef.valid_values.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
        <StatusHint s={status} />
      </div>
    );
  }

  // String / string | null
  const strVal = typeof value === "string" ? value : String(value ?? "");
  const longText = (fieldDef.min_words ?? 0) > 0 || strVal.length > 80;
  const isCode = fieldDef.path.includes("execution_example");

  return (
    <div style={{ paddingLeft: "28px" }}>
      {longText ? (
        <textarea
          value={strVal}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`${humanize(fieldDef.path.split(".").pop() ?? "")}…`}
          rows={isCode ? 5 : 3}
          className={`w-full text-[11px] leading-relaxed text-[#4a4a6a] bg-white border rounded px-3 py-2 focus:outline-none resize-none ${borderCls(status)}`}
          style={{
            fontFamily: isCode
              ? "var(--font-jetbrains,monospace)"
              : "var(--font-dm-sans,'DM Sans'),system-ui,sans-serif",
          }}
        />
      ) : (
        <input
          value={strVal}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`${humanize(fieldDef.path.split(".").pop() ?? "")}…`}
          className={`w-full text-[11px] text-[#4a4a6a] bg-white border rounded px-3 py-1.5 focus:outline-none ${borderCls(status)}`}
          style={{ fontFamily: "var(--font-dm-sans,'DM Sans'),system-ui,sans-serif" }}
        />
      )}
      <StatusHint s={status} />
    </div>
  );
}

function StatusHint({ s }: { s: FieldStatus }) {
  if (s === "required") return <p className="text-[10px] text-red-500 mt-0.5">Campo obligatorio</p>;
  if (s === "review") return <p className="text-[10px] text-amber-500 mt-0.5">Requiere revisión humana</p>;
  return null;
}

function AuditHint({ issue }: { issue: AuditIssue }) {
  return (
    <div className="mt-1.5 rounded px-2.5 py-2 bg-orange-50 border border-orange-200 text-[10px] text-orange-900 space-y-1">
      <p className="font-semibold leading-snug">⚠ {issue.issue}</p>
      {issue.suggestion && (
        <p className="opacity-80 leading-snug">💡 {issue.suggestion}</p>
      )}
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  doc: Document;
  editing: boolean;
  onSave: () => void;
  onCancelEdit: () => void;
  saveRef?: React.MutableRefObject<(() => Promise<void>) | null>;
  onValidationChange?: (canSave: boolean) => void;
  auditIssues?: AuditIssue[] | null;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function DocInlineEditor({
  doc, editing, onSave, onCancelEdit, saveRef, onValidationChange, auditIssues,
}: Props) {
  const spec = useDocSpec(doc.object_type);
  const content = doc.content as Record<string, unknown>;

  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Initialize form when spec loads (or when switching docs)
  useEffect(() => {
    if (spec) setFormValues(initFormState(content, spec));
  }, [spec, doc.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Validation: required HUMANO/PARCIAL non-array fields must be non-empty
  const requiredEditableFields = spec?.sections
    .flatMap((s) => s.fields)
    .filter((f) => f.required && f.completion !== "AUTO" && !f.is_array) ?? [];

  const hasBlockingErrors = requiredEditableFields.some((f) => {
    const v = formValues[f.path];
    if (Array.isArray(v)) return v.length === 0;
    if (typeof v === "boolean") return false; // true/false son selecciones válidas
    const str = typeof v === "string" ? v.trim() : "";
    return str === "" || str.startsWith("[REQUIERE");
  });

  const canSave = !hasBlockingErrors && !saving;

  useEffect(() => {
    onValidationChange?.(canSave);
  }, [canSave]); // eslint-disable-line react-hooks/exhaustive-deps

  const setField = (path: string, val: unknown) =>
    setFormValues((prev) => ({ ...prev, [path]: val }));

  async function handleSave() {
    if (!spec) return;
    setSaving(true);
    setError("");
    try {
      const updatedContent = buildUpdatedContent(content, formValues);
      const body: Record<string, unknown> = { content: updatedContent };
      // Sync top-level name if physical_name was edited
      const newName = formValues["identification.physical_name"];
      if (typeof newName === "string" && newName && newName !== doc.name) body.name = newName;
      await patchDocument(doc.id, body);
      onSave();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  if (saveRef && editing) saveRef.current = handleSave;

  // ── Read mode — delegate to DocViewer ────────────────────────────────────
  if (!editing) return <DocViewer doc={doc} />;

  // ── Loading state ─────────────────────────────────────────────────────────
  if (!spec) {
    return (
      <div className="h-full overflow-y-auto flex items-center justify-center">
        <span className="text-sm text-[#9090b0]">Cargando…</span>
      </div>
    );
  }

  // ── Edit mode ─────────────────────────────────────────────────────────────
  const statusMap: Record<string, [string, string]> = {
    approved:  ["approved",  "Aprobado"],
    draft:     ["draft",     "Borrador"],
    delisted:  ["delisted",  "Deslistado"],
  };
  const [statusCls, statusLabel] = statusMap[doc.status] ?? ["draft", doc.status];
  const typeLabel = doc.object_type.replace(/_/g, " ").toUpperCase();

  // Header values read from saved content (read-only in header)
  const physName = String(getNestedValue(content, "identification.physical_name") || doc.name);
  const bizDomain = String(formValues["identification.business_domain"] ?? getNestedValue(content, "identification.business_domain") ?? "");
  const techOwner = String(formValues["governance.technical_owner"] ?? getNestedValue(content, "governance.technical_owner") ?? "");
  const lastUpdated = String(getNestedValue(content, "governance.doc_last_updated") || "—").slice(0, 10);

  return (
    <div className="h-full overflow-y-auto">
      {error && (
        <div className="mx-6 mt-4 text-xs text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded">
          {error}
        </div>
      )}

      <div className="doc-page" style={{ padding: "40px 48px", maxWidth: "100%" }}>

        {/* Eyebrow */}
        <div className="doc-eyebrow">
          <span className="doc-type-pill">{typeLabel}</span>
          <span className="doc-domain">{bizDomain || "—"}</span>
          <span style={{ flex: 1 }} />
          <span className={`status-badge ${statusCls}`}>
            <span className="status-dot" />{statusLabel}
          </span>
        </div>

        {/* Title (read-only — AUTO field) */}
        <h1 className="doc-title">{physName}</h1>

        <hr className="doc-rule" style={{ margin: "16px 0 20px" }} />

        {/* Meta bar */}
        <div className="doc-meta-bar">
          <div className="meta-item">
            <div className="meta-label">Dominio</div>
            <div className="meta-value">{bizDomain || "—"}</div>
          </div>
          <div className="meta-item">
            <div className="meta-label">Owner técnico</div>
            <div className="meta-value">{techOwner || "—"}</div>
          </div>
          <div className="meta-item">
            <div className="meta-label">Última actualización</div>
            <div className="meta-value">{lastUpdated}</div>
          </div>
        </div>

        {/* Editable sections — only HUMANO + PARCIAL fields */}
        {spec.sections.map((section, idx) => {
          const editableFields = section.fields.filter((f) => f.completion !== "AUTO");
          if (!editableFields.length) return null;

          return (
            <div key={section.key} className="section">
              <SectionHeading num={String(idx + 1).padStart(2, "0")} title={section.label} />
              {editableFields.map((fieldDef) => {
                const fieldName = fieldDef.path.split(".").pop() ?? fieldDef.path;
                const auditIssue = auditIssues?.find((i) => i.field === fieldDef.path) ?? null;
                return (
                  <div key={fieldDef.path} className="field-entry">
                    <div className="field-label">
                      {humanize(fieldName)}
                      {fieldDef.completion === "HUMANO" && (
                        <span className="humano-badge">HUMANO</span>
                      )}
                      {!fieldDef.required && (
                        <span className="optional-badge">OPT</span>
                      )}
                      {(fieldDef.completion === "HUMANO" || fieldDef.completion === "PARCIAL") && fieldDef.user_help && (
                        <span className="help-icon" title={fieldDef.user_help}>?</span>
                      )}
                    </div>
                    <FieldEditor
                      fieldDef={fieldDef}
                      value={formValues[fieldDef.path] ?? ""}
                      onChange={(v) => setField(fieldDef.path, v)}
                    />
                    {auditIssue && <AuditHint issue={auditIssue} />}
                  </div>
                );
              })}
            </div>
          );
        })}

        {/* Footer */}
        <div className="doc-footer">
          <div className="doc-footer-left">
            Generado por memorIA · Creado por {doc.created_by}<br />
            Este documento es la fuente oficial de verdad para este objeto.
          </div>
          <div className="doc-footer-right">{physName}</div>
        </div>

      </div>
    </div>
  );
}
