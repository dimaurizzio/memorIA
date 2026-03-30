"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { Search } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { DocPanel } from "@/components/doc-panel";
import { useStore } from "@/lib/store";
import { getDocumentsForUser, deleteDocument } from "@/lib/api";
import { useObjectTypes } from "@/lib/hooks";
import type { Document, DocStatus, ObjectType } from "@/lib/types";

export function DocumentosPage() {
  const { panelDocId, openPanel, closePanel, user, role } = useStore();
  const objectTypes = useObjectTypes();
  const [statusFilter, setStatusFilter] = useState<string>("todos");
  const [typeFilter, setTypeFilter] = useState<string>("todos");
  const [search, setSearch] = useState("");

  const extra: Record<string, string> = {};
  if (statusFilter !== "todos") extra.status = statusFilter;
  if (typeFilter !== "todos") extra.object_type = typeFilter;

  const { data: docs = [], isLoading } = useSWR(
    ["documents", statusFilter, typeFilter, user, role],
    () => getDocumentsForUser(user, role, extra),
    { revalidateOnFocus: true }
  );

  const filtered = search
    ? docs.filter((d) => d.name.toLowerCase().includes(search.toLowerCase()))
    : docs;

  async function handleDelete(doc: Document) {
    if (!confirm(`¿Eliminar "${doc.name}"?`)) return;
    await deleteDocument(doc.id);
    if (panelDocId === doc.id) closePanel();
    globalMutate(["documents", statusFilter, typeFilter, user, role]);
  }

  const hasPanel = !!panelDocId;
  const n = hasPanel ? 2 : 3;

  return (
    <div className="flex h-full">
      {/* Gallery */}
      <div className={`flex flex-col h-full ${hasPanel ? "w-[45%]" : "w-full"} transition-all duration-200 overflow-hidden`}>
        {/* Filters */}
        <div className="px-4 pt-4 pb-3 border-b border-[#d4d4c8] bg-[#fafaf8] flex-shrink-0 space-y-2">
          <h1
            className="text-base font-bold text-[#1a1a2e]"
            style={{ fontFamily: "var(--font-lora, Lora), serif" }}
          >
            Documentos
          </h1>
          <div className="flex gap-2 flex-wrap items-center">
            <select
              className="text-xs px-2 py-1.5 rounded border border-[#d4d4c8] bg-white text-[#4a4a6a] focus:outline-none focus:border-[#2563b0]"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="todos">Todos los estados</option>
              <option value="draft">Borrador</option>
              <option value="approved">Aprobado</option>
              <option value="rejected">Rechazado</option>
            </select>
            <select
              className="text-xs px-2 py-1.5 rounded border border-[#d4d4c8] bg-white text-[#4a4a6a] focus:outline-none focus:border-[#2563b0]"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="todos">Todos los tipos</option>
              {objectTypes.map((t) => (
                <option key={t.value} value={t.value}>{t.icon} {t.display_name}</option>
              ))}
            </select>
            <div className="flex items-center gap-1.5 flex-1 min-w-[120px]">
              <Search size={12} className="text-[#9090b0] flex-shrink-0" />
              <input
                className="w-full text-xs bg-transparent text-[#4a4a6a] focus:outline-none placeholder:text-[#9090b0]"
                placeholder="Buscar…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <p className="text-xs text-[#9090b0] text-center mt-8">Cargando…</p>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-[#9090b0] text-center mt-8">No hay documentos con esos filtros.</p>
          ) : (
            <div
              className="grid gap-3"
              style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}
            >
              {filtered.map((doc) => {
                const isSel = doc.id === panelDocId;
                const canManage = role === "admin" || doc.created_by === user;
                const canDelete = doc.status !== "approved" && canManage;
                const icon = objectTypes.find((t) => t.value === doc.object_type)?.icon ?? "📄";
                return (
                  <div
                    key={doc.id}
                    className="rounded-lg p-3 border-2 transition-colors cursor-pointer"
                    style={{
                      borderColor: isSel ? "#3b82f6" : "#e5e7eb",
                      background: isSel ? "#eff6ff" : "white",
                    }}
                    onClick={() => openPanel(doc.id, "viewer")}
                  >
                    <div className="text-lg mb-1">{icon}</div>
                    <div className="font-semibold text-xs text-[#111827] mb-0.5 truncate">{doc.name}</div>
                    <div className="text-[10px] text-[#9090b0] uppercase tracking-wide mb-2">{doc.object_type}</div>
                    <div className="flex items-center justify-between gap-1">
                      <StatusBadge status={doc.status as DocStatus} />
                      {canDelete && (
                        <button
                          className="text-[#9090b0] hover:text-red-500 transition-colors p-0.5"
                          onClick={(e) => { e.stopPropagation(); handleDelete(doc); }}
                          title="Eliminar"
                        >
                          🗑
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Panel */}
      {hasPanel && (
        <div className="flex-1 h-full">
          <DocPanel />
        </div>
      )}
    </div>
  );
}
