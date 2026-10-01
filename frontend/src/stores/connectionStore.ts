import { create } from "zustand";
import type { Connection } from "../types";
import { apiClient } from "../services/api";

// ── Catalog types ────────────────────────────────────────────────────────────
export interface AppDefinition {
  app_id: string;
  name: string;
  description: string;
  icon_emoji: string;
  category: string;
  connection_type: string;
  auth_label: string;
  auth_instructions: string;
  requires_credentials: boolean;
  capabilities: string[];
  risk_profile: string;
  available: boolean;
  docs_url?: string;
}

export interface HealthCheckResult {
  connection_id: string;
  status: "healthy" | "degraded" | "unavailable";
  message: string;
  checked_at: string;
}

// ── Store state ──────────────────────────────────────────────────────────────
interface ConnectionState {
  connections: Connection[];
  catalog: AppDefinition[];
  isLoading: boolean;
  catalogLoading: boolean;
  error: string | null;

  fetchConnections: () => Promise<Connection[]>;
  fetchCatalog: () => Promise<void>;
  connectApp: (connectionId: string, payload: { token?: string; url?: string; credentials?: object }) => Promise<void>;
  disconnectApp: (connectionId: string) => Promise<void>;
  togglePermission: (connectionId: string, permissionKey: string, isGranted: boolean) => Promise<void>;
  registerMCPServer: (payload: { name: string; url: string; description?: string }) => Promise<void>;
  removeMCPServer: (connectionId: string) => Promise<void>;

  // P2-4 new actions
  initConnection: (appId: string) => Promise<string>;
  connectWithToken: (connectionId: string, token: string) => Promise<void>;
  testConnectionHealth: (connectionId: string) => Promise<HealthCheckResult>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  connections: [],
  catalog: [],
  isLoading: false,
  catalogLoading: false,
  error: null,

  fetchConnections: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await apiClient.get<Connection[]>("/api/connections");
      set({ connections: data, isLoading: false });
      return data;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load connections";
      set({ isLoading: false, error: msg });
      throw err;
    }
  },

  fetchCatalog: async () => {
    set({ catalogLoading: true });
    try {
      const data = await apiClient.get<AppDefinition[]>("/api/catalog");
      set({ catalog: data, catalogLoading: false });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load catalog";
      set({ catalogLoading: false, error: msg });
    }
  },

  initConnection: async (appId: string) => {
    const result = await apiClient.post<{ connection_id: string; status: string }>(
      `/api/connections/catalog/${appId}/init`,
      {}
    );
    await get().fetchConnections();
    return result.connection_id;
  },

  connectWithToken: async (connectionId: string, token: string) => {
    await apiClient.post(`/api/connections/${connectionId}/connect`, { token });
    await get().fetchConnections();
  },

  testConnectionHealth: async (connectionId: string) => {
    const result = await apiClient.get<HealthCheckResult>(
      `/api/connections/${connectionId}/health`
    );
    await get().fetchConnections(); // Refresh status after health check
    return result;
  },

  connectApp: async (connectionId, payload) => {
    try {
      await apiClient.post(`/api/connections/${connectionId}/connect`, payload);
      await get().fetchConnections();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to connect application";
      set({ error: msg });
      throw err;
    }
  },

  disconnectApp: async (connectionId) => {
    try {
      await apiClient.post(`/api/connections/${connectionId}/disconnect`);
      await get().fetchConnections();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to disconnect application";
      set({ error: msg });
      throw err;
    }
  },

  registerMCPServer: async (payload) => {
    try {
      await apiClient.post("/api/connections/mcp/register", payload);
      await get().fetchConnections();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to register MCP server";
      set({ error: msg });
      throw err;
    }
  },

  removeMCPServer: async (connectionId) => {
    try {
      await apiClient.delete(`/api/connections/mcp/${connectionId}`);
      await get().fetchConnections();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to remove MCP server";
      set({ error: msg });
      throw err;
    }
  },

  togglePermission: async (connectionId, permissionKey, isGranted) => {
    try {
      set((state) => ({
        connections: state.connections.map((c) =>
          c.id === connectionId
            ? {
                ...c,
                permissions: c.permissions.map((p) =>
                  p.key === permissionKey ? { ...p, is_granted: isGranted } : p
                ),
              }
            : c
        ),
      }));
      await apiClient.post(`/api/connections/${connectionId}/permissions`, {
        permissions: [{ permission_key: permissionKey, is_granted: isGranted }],
      });
    } catch (err: unknown) {
      await get().fetchConnections();
      const msg = err instanceof Error ? err.message : "Failed to update permission";
      set({ error: msg });
      throw err;
    }
  },
}));
