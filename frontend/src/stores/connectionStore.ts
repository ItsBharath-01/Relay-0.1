import { create } from "zustand";
import type { Connection } from "../types";
import { apiClient } from "../services/api";

interface ConnectionState {
  connections: Connection[];
  isLoading: boolean;
  error: string | null;

  fetchConnections: () => Promise<Connection[]>;
  connectApp: (connectionId: string, payload: { token?: string; url?: string; credentials?: any }) => Promise<void>;
  disconnectApp: (connectionId: string) => Promise<void>;
  togglePermission: (connectionId: string, permissionKey: string, isGranted: boolean) => Promise<void>;
  
  registerMCPServer: (payload: { name: string; url: string; description?: string }) => Promise<void>;
  removeMCPServer: (connectionId: string) => Promise<void>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  connections: [],
  isLoading: false,
  error: null,

  fetchConnections: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await apiClient.get<Connection[]>("/api/connections");
      set({ connections: data, isLoading: false });
      return data;
    } catch (err: any) {
      set({ isLoading: false, error: err.message || "Failed to load connections" });
      throw err;
    }
  },

  connectApp: async (connectionId, payload) => {
    try {
      await apiClient.post(`/api/connections/${connectionId}/connect`, payload);
      await get().fetchConnections();
    } catch (err: any) {
      set({ error: err.message || "Failed to connect application" });
      throw err;
    }
  },

  disconnectApp: async (connectionId) => {
    try {
      await apiClient.post(`/api/connections/${connectionId}/disconnect`);
      await get().fetchConnections();
    } catch (err: any) {
      set({ error: err.message || "Failed to disconnect application" });
      throw err;
    }
  },

  registerMCPServer: async (payload) => {
    try {
      await apiClient.post("/api/connections/mcp/register", payload);
      await get().fetchConnections();
    } catch (err: any) {
      set({ error: err.message || "Failed to register MCP server" });
      throw err;
    }
  },

  removeMCPServer: async (connectionId) => {
    try {
      await apiClient.delete(`/api/connections/mcp/${connectionId}`);
      await get().fetchConnections();
    } catch (err: any) {
      set({ error: err.message || "Failed to remove MCP server" });
      throw err;
    }
  },

  togglePermission: async (connectionId, permissionKey, isGranted) => {
    try {
      // Optimistic update
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
    } catch (err: any) {
      // Rollback on error
      await get().fetchConnections();
      set({ error: err.message || "Failed to update permission" });
      throw err;
    }
  },
}));
