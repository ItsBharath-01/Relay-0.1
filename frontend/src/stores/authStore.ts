import { create } from "zustand";
import type { User, UserPreference } from "../types";
import { apiClient } from "../services/api";

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  checkAuth: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  updatePreferences: (prefs: Partial<UserPreference>) => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem("relay_token"),
  isAuthenticated: false,
  isLoading: true,
  error: null,

  checkAuth: async () => {
    const token = localStorage.getItem("relay_token");
    if (!token) {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return;
    }

    try {
      apiClient.setToken(token);
      const user = await apiClient.get<User>("/api/auth/me");
      set({ user, isAuthenticated: true, isLoading: false, error: null });
    } catch (err: any) {
      apiClient.setToken(null);
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
    }
  },

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await apiClient.post<{ access_token: string; token_type: string; user: User }>(
        "/api/auth/login",
        { email, password }
      );
      apiClient.setToken(res.access_token);
      set({
        token: res.access_token,
        user: res.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      set({ isLoading: false, error: err.message || "Failed to sign in" });
      throw err;
    }
  },

  signup: async (name: string, email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await apiClient.post<{ access_token: string; token_type: string; user: User }>(
        "/api/auth/signup",
        { name, email, password }
      );
      apiClient.setToken(res.access_token);
      set({
        token: res.access_token,
        user: res.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      set({ isLoading: false, error: err.message || "Failed to create account" });
      throw err;
    }
  },

  logout: () => {
    apiClient.setToken(null);
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },

  updatePreferences: async (prefs: Partial<UserPreference>) => {
    try {
      const current = get().user?.preferences || {
        language: "en",
        auto_recover: true,
        ask_external_messages: true,
        ask_payments: true,
        ask_purchases: true,
        ask_deleting: true,
        ask_sensitive_info: true,
        threshold_people: 1,
        threshold_amount: 0,
      };
      const merged = { ...current, ...prefs };
      const updated = await apiClient.put<UserPreference>("/api/auth/preferences", merged);
      const currentUser = get().user;
      if (currentUser) {
        set({ user: { ...currentUser, preferences: updated } });
      }
    } catch (err: any) {
      set({ error: err.message || "Failed to update preferences" });
      throw err;
    }
  },

  clearError: () => set({ error: null }),
}));
