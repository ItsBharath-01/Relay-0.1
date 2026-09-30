import { create } from "zustand";
import type { Approval } from "../types";
import { apiClient } from "../services/api";

interface ApprovalState {
  approvals: Approval[];
  pendingCount: number;
  isLoading: boolean;
  error: string | null;

  fetchApprovals: (statusFilter?: string) => Promise<Approval[]>;
  decide: (approvalId: string, decision: "approved" | "rejected", reason?: string) => Promise<void>;
}

export const useApprovalStore = create<ApprovalState>((set) => ({
  approvals: [],
  pendingCount: 0,
  isLoading: false,
  error: null,

  fetchApprovals: async (statusFilter?: string) => {
    set({ isLoading: true, error: null });
    try {
      const endpoint = statusFilter ? `/api/approvals?status_filter=${statusFilter}` : "/api/approvals";
      const data = await apiClient.get<Approval[]>(endpoint);
      const pendingCount = data.filter((a) => a.status === "pending").length;
      set({ approvals: data, pendingCount, isLoading: false });
      return data;
    } catch (err: any) {
      set({ isLoading: false, error: err.message || "Failed to fetch approvals" });
      throw err;
    }
  },

  decide: async (approvalId, decision, reason) => {
    try {
      await apiClient.post(`/api/approvals/${approvalId}/decide`, {
        decision,
        reason,
        decided_by: "ui",
      });

      // Update local state
      set((state) => {
        const updated = state.approvals.map((a) =>
          a.id === approvalId ? { ...a, status: decision } : a
        );
        const pendingCount = updated.filter((a) => a.status === "pending").length;
        return { approvals: updated, pendingCount };
      });
    } catch (err: any) {
      set({ error: err.message || "Failed to record approval decision" });
      throw err;
    }
  },
}));
