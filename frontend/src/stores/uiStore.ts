import { create } from "zustand";
import type { LLMHealth } from "../types";
import { apiClient } from "../services/api";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info" | "warning";
  title?: string;
  message: string;
  duration?: number;
}

interface UIState {
  llmHealth: LLMHealth | null;
  isCheckingLLM: boolean;
  sidebarCollapsed: boolean;
  mobileMenuOpen: boolean;
  toasts: ToastMessage[];

  checkLLMHealth: () => Promise<LLMHealth>;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileMenuOpen: (open: boolean) => void;
  addToast: (toast: Omit<ToastMessage, "id">) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  llmHealth: null,
  isCheckingLLM: false,
  sidebarCollapsed: false,
  mobileMenuOpen: false,
  toasts: [],

  checkLLMHealth: async () => {
    set({ isCheckingLLM: true });
    try {
      const data = await apiClient.get<LLMHealth>("/api/health/llm");
      set({ llmHealth: data, isCheckingLLM: false });
      return data;
    } catch (err: any) {
      const fallback: LLMHealth = {
        provider: "ollama",
        model: "qwen3:4b",
        reachable: false,
        available: false,
        status: "backend_unavailable",
        error: err.message || "Failed to connect to backend",
      };
      set({ llmHealth: fallback, isCheckingLLM: false });
      return fallback;
    }
  },

  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setMobileMenuOpen: (open) => set({ mobileMenuOpen: open }),

  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastMessage = { ...toast, id, duration: toast.duration ?? 4000 };
    set((state) => ({ toasts: [...state.toasts, newToast] }));

    if (newToast.duration && newToast.duration > 0) {
      setTimeout(() => {
        get().removeToast(id);
      }, newToast.duration);
    }
  },

  removeToast: (id: string) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },
}));
