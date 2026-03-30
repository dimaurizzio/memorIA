import { create } from "zustand";
import type { ChatMessage, PendingPanel } from "./types";

interface AppState {
  // User (simple, no auth)
  user: string;
  role: "developer" | "admin";
  setUser: (user: string) => void;
  setRole: (role: "developer" | "admin") => void;

  // Panel lateral
  panelDocId: string | null;
  panelMode: "viewer" | "editor";
  openPanel: (docId: string, mode?: "viewer" | "editor") => void;
  closePanel: () => void;
  applyPendingPanel: (p: PendingPanel) => void;

  // Chat history
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
}

export const useStore = create<AppState>((set) => ({
  user: "dev@empresa.com",
  role: "developer",
  setUser: (user) => set({ user }),
  setRole: (role) => set({ role }),

  panelDocId: null,
  panelMode: "viewer",
  openPanel: (docId, mode = "viewer") => set({ panelDocId: docId, panelMode: mode }),
  closePanel: () => set({ panelDocId: null }),
  applyPendingPanel: (p) => set({ panelDocId: p.doc_id, panelMode: p.mode }),

  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
}));
