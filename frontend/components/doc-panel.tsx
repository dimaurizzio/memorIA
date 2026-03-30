"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { X, Download, Pencil, ShieldCheck, RefreshCw, Trash2, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DocViewer } from "@/components/doc-viewer";
import { DocInlineEditor } from "@/components/doc-inline-editor";
import { useStore } from "@/lib/store";
import { getDocument, auditDocument, refreshDocument, deleteDocument, overrideDocument, downloadPdf } from "@/lib/api";
import type { AuditResult } from "@/lib/types";

export function DocPanel() {
  const { panelDocId, closePanel, openPanel, user, role } = useStore();
  const [isEditing, setIsEditing] = useState(false);
  const [editorCanSave, setEditorCanSave] = useState(false);
  const saveRef = useRef<(() => Promise<void>) | null>(null);
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [overrideStatus, setOverrideStatus] = useState<"approved" | "delisted">("approved");
  const prevDocIdRef = useRef<string | null>(null);
  const [overrideNotes, setOverrideNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const { data: doc, isLoading } = useSWR(
    panelDocId ? `doc:${panelDocId}` : null,
    () => getDocument(panelDocId!),
    {
      revalidateOnFocus: false,
      onSuccess: (data) => {
        // Solo resetea el modo de edición al cambiar de documento, no al recargar el mismo
        if (prevDocIdRef.current !== null && prevDocIdRef.current !== data?.id) {
          setIsEditing(false);
        }
        prevDocIdRef.current = data?.id ?? null;
      },
    }
  );

  const reloadDoc = useCallback(() => {
    globalMutate(`doc:${panelDocId}`);
    globalMutate((key) => Array.isArray(key) && key[0] === "documents");
  }, [panelDocId]);

  if (!panelDocId) return null;

  const canManage = role === "admin" || doc?.created_by === user;
  const status = doc?.status;

  async function handleAudit() {
    if (!doc) return;
    setBusy(true);
    try {
      const res = await auditDocument(doc.id, user);
      setAuditResult({ result: res.result, issues: res.issues });
      reloadDoc();
      // Si no fue aprobado, abrir el editor para que el autor vea las sugerencias por campo
      if (res.result !== "approved") {
        setIsEditing(true);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRefresh() {
    if (!doc) return;
    setBusy(true);
    try {
      await refreshDocument(doc.id, user);
      reloadDoc();
      setIsEditing(true);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!doc || !confirm("¿Eliminar este documento?")) return;
    await deleteDocument(doc.id);
    closePanel();
    globalMutate((key) => Array.isArray(key) && key[0] === "documents");
  }

  async function handleOverride() {
    if (!doc) return;
    await overrideDocument(doc.id, { new_status: overrideStatus, notes: overrideNotes, overridden_by: user });
    reloadDoc();
  }

  return (
    <div className="flex flex-col h-full border-l border-[#d4d4c8] bg-[#fafaf8] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#d4d4c8] flex-shrink-0">
        <span className="text-sm font-medium text-[#1a1a2e] truncate">
          {doc?.name || "Cargando…"}
        </span>
        <button
          onClick={closePanel}
          className="p-1 rounded hover:bg-[#f0f0ea] text-[#9090b0] hover:text-[#1a1a2e] transition-colors"
        >
          <X size={15} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading || !doc ? (
          <div className="flex items-center justify-center h-full text-sm text-[#9090b0]">
            Cargando…
          </div>
        ) : status === "draft" ? (
          <DocInlineEditor
            doc={doc}
            editing={isEditing}
            onSave={() => { reloadDoc(); setIsEditing(false); }}
            onCancelEdit={() => setIsEditing(false)}
            saveRef={saveRef}
            onValidationChange={setEditorCanSave}
            auditIssues={auditResult?.issues ?? doc.last_audit_issues ?? null}
          />
        ) : (
          <DocViewer doc={doc} />
        )}
      </div>

      {/* Actions */}
      {doc && (
        <div className="border-t border-[#d4d4c8] px-3 py-2.5 flex-shrink-0 space-y-2">
          <div className="flex gap-2 flex-wrap items-center">
            {/* PDF */}
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7 border-[#d4d4c8] text-[#4a4a6a] hover:bg-[#f0f0ea]"
              onClick={() => downloadPdf(doc.id, doc.name)}
            >
              <Download size={12} className="mr-1" /> PDF
            </Button>

            {/* Edit */}
            {status === "draft" && canManage && !isEditing && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 border-[#d4d4c8] text-[#4a4a6a] hover:bg-[#f0f0ea]"
                onClick={() => setIsEditing(true)}
              >
                <Pencil size={12} className="mr-1" /> Editar
              </Button>
            )}

            {/* Audit */}
            {status === "draft" && !isEditing && (
              <Button
                size="sm"
                className="text-xs h-7 bg-[#2563b0] hover:bg-[#1d4ed8] text-white"
                onClick={handleAudit}
                disabled={busy}
              >
                <ShieldCheck size={12} className="mr-1" />
                {busy ? "Auditando…" : "Auditar"}
              </Button>
            )}

            {/* Refresh */}
            {status === "approved" && canManage && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 border-[#d4d4c8] text-[#4a4a6a] hover:bg-[#f0f0ea]"
                onClick={handleRefresh}
                disabled={busy}
              >
                <RefreshCw size={12} className="mr-1" />
                {busy ? "Regenerando…" : "Actualizar"}
              </Button>
            )}

            {/* Delete */}
            {status !== "approved" && canManage && !isEditing && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 border-red-200 text-red-600 hover:bg-red-50"
                onClick={handleDelete}
              >
                <Trash2 size={12} />
              </Button>
            )}

            {/* Override */}
            {role === "admin" && !isEditing && (
              <Popover>
                <PopoverTrigger className="inline-flex items-center gap-1 text-xs h-7 px-2.5 rounded-md border border-[#d4d4c8] text-[#4a4a6a] bg-white hover:bg-[#f0f0ea] transition-colors">
                  <Settings size={12} /> Override
                </PopoverTrigger>
                <PopoverContent className="w-56 p-3 space-y-2">
                  <Select
                    value={overrideStatus}
                    onValueChange={(v) => setOverrideStatus(v as "approved" | "delisted")}
                  >
                    <SelectTrigger className="h-7 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="approved">Aprobado</SelectItem>
                      <SelectItem value="delisted">Deslistado</SelectItem>
                    </SelectContent>
                  </Select>
                  <input
                    className="w-full text-xs px-2 py-1.5 rounded border border-[#d4d4c8] focus:outline-none focus:border-[#2563b0]"
                    placeholder="Notas"
                    value={overrideNotes}
                    onChange={(e) => setOverrideNotes(e.target.value)}
                  />
                  <Button
                    size="sm"
                    className="w-full text-xs h-7 bg-[#2563b0] hover:bg-[#1d4ed8] text-white"
                    onClick={handleOverride}
                  >
                    Aplicar
                  </Button>
                </PopoverContent>
              </Popover>
            )}

            {/* Guardar / Cancelar — solo en modo edición, alineados a la derecha */}
            {isEditing && (
              <>
                <span className="flex-1" />
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-7 border-[#d4d4c8] text-[#4a4a6a]"
                  onClick={() => setIsEditing(false)}
                >
                  Cancelar
                </Button>
                <Button
                  size="sm"
                  className="text-xs h-7 bg-[#2563b0] hover:bg-[#1d4ed8] text-white disabled:opacity-50"
                  onClick={() => saveRef.current?.()}
                  disabled={!editorCanSave}
                  title={!editorCanSave ? "Completá los campos en rojo antes de guardar" : undefined}
                >
                  Guardar cambios
                </Button>
              </>
            )}
          </div>

          {/* Audit result */}
          {auditResult && (
            <div
              className={`rounded p-2.5 text-xs space-y-1 ${
                auditResult.result === "approved"
                  ? "bg-green-50 border border-green-200 text-green-800"
                  : "bg-yellow-50 border border-yellow-200 text-yellow-800"
              }`}
            >
              <p className="font-semibold">
                {auditResult.result === "approved"
                  ? "✅ Aprobado — el documento fue indexado."
                  : `🟡 Con observaciones (${auditResult.issues.length}) — revisá los campos marcados en el editor.`}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
