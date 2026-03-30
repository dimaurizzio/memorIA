import type { Document, AuditResult, ChatMessage, PendingPanel, ObjectTypeInfo, DocSpec } from "./types";

const API = typeof window === "undefined" ? "http://localhost:8000" : "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText);
  }
  return r.json();
}

// Documents
export const getDocuments = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return req<Document[]>(`/documents${qs}`);
};

export const getDocumentsForUser = (
  user: string,
  role: string,
  extra?: Record<string, string>
) => getDocuments({ user_id: user, role, ...extra });

export const getDocument = (id: string) => req<Document>(`/documents/${id}`);

export const patchDocument = (id: string, body: object) =>
  req<Document>(`/documents/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteDocument = (id: string) =>
  req<{ ok: boolean }>(`/documents/${id}`, { method: "DELETE" });

export const generateDocument = (body: {
  object_type: string;
  object_name: string;
  created_by: string;
}) => req<{ document_id: string }>(`/documents/generate`, { method: "POST", body: JSON.stringify(body) });

export const auditDocument = (id: string, audited_by: string) =>
  req<AuditResult & { document_id: string }>(`/documents/${id}/audit`, {
    method: "POST",
    body: JSON.stringify({ audited_by }),
  });

export const refreshDocument = (id: string, requested_by: string) =>
  req<{ document_id: string }>(`/documents/${id}/refresh`, {
    method: "POST",
    body: JSON.stringify({ requested_by }),
  });

export const overrideDocument = (
  id: string,
  body: { new_status: string; notes: string; overridden_by: string }
) => req(`/admin/documents/${id}/override`, { method: "POST", body: JSON.stringify(body) });

export async function downloadPdf(id: string, name: string) {
  const r = await fetch(`${API}/documents/${id}/pdf`);
  if (!r.ok) throw new Error(await r.text());
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// Spec
export const getObjectTypes = () => req<ObjectTypeInfo[]>("/spec/types");
export const getDocSpec = (objectType: string) => req<DocSpec>(`/spec/${objectType}`);

// Chat
export const sendChat = (body: {
  message: string;
  history: ChatMessage[];
  user: string;
}): Promise<{ response: string; pending_panel: PendingPanel | null }> =>
  req("/chat", { method: "POST", body: JSON.stringify(body) });
