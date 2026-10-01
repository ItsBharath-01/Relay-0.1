import { create } from "zustand";
import type { ExecutionDetail, ExecutionEvent, Approval, Recovery, Verification } from "../types";
import { apiClient } from "../services/api";

interface ExecutionState {
  execution: ExecutionDetail | null;
  events: ExecutionEvent[];
  pendingApproval: Approval | null;
  recoveries: Recovery[];
  verifications: Verification[];
  isStreaming: boolean;
  isReconnecting: boolean;
  error: string | null;
  eventSource: EventSource | null;

  startExecution: (planId: string) => Promise<ExecutionDetail>;
  fetchExecution: (executionId: string) => Promise<ExecutionDetail>;
  subscribeToStream: (executionId: string) => void;
  unsubscribeFromStream: () => void;
  pauseExecution: () => Promise<void>;
  resumeExecution: () => Promise<void>;
  cancelExecution: () => Promise<void>;
  decideApproval: (approvalId: string, decision: "approved" | "rejected", reason?: string) => Promise<void>;
  applyEvent: (event: ExecutionEvent) => void;
  reset: () => void;
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  execution: null,
  events: [],
  pendingApproval: null,
  recoveries: [],
  verifications: [],
  isStreaming: false,
  isReconnecting: false,
  error: null,
  eventSource: null,

  startExecution: async (planId: string) => {
    set({ error: null, events: [], recoveries: [], verifications: [], pendingApproval: null });
    try {
      const exec = await apiClient.post<ExecutionDetail>("/api/executions/start", {
        plan_id: planId,
      });

      set({
        execution: exec,
        events: exec.events || [],
        recoveries: exec.recoveries || [],
        verifications: exec.verifications || [],
      });

      // Automatically subscribe to live SSE event stream
      get().subscribeToStream(exec.id);

      return exec;
    } catch (err: any) {
      set({ error: err.message || "Failed to start execution" });
      throw err;
    }
  },

  fetchExecution: async (executionId: string) => {
    try {
      const exec = await apiClient.get<ExecutionDetail>(`/api/executions/${executionId}`);
      const pending = exec.approvals?.find((a) => a.status === "pending") || null;

      set({
        execution: exec,
        events: exec.events || [],
        recoveries: exec.recoveries || [],
        verifications: exec.verifications || [],
        pendingApproval: pending,
        error: null,
      });

      return exec;
    } catch (err: any) {
      set({ error: err.message || "Failed to fetch execution" });
      throw err;
    }
  },

  subscribeToStream: (executionId: string) => {
    // Unsubscribe from any previous source
    get().unsubscribeFromStream();

    const streamUrl = apiClient.createEventSourceUrl(`/api/executions/${executionId}/events`);
    const es = new EventSource(streamUrl);

    set({ eventSource: es, isStreaming: true, isReconnecting: false });

    es.onopen = () => {
      set({ isStreaming: true, isReconnecting: false });
    };

    es.onmessage = (messageEvent) => {
      try {
        const data: ExecutionEvent = JSON.parse(messageEvent.data);
        get().applyEvent(data);
      } catch (e) {
        // Ping or non-json keep-alive
      }
    };

    // Also register specific event type listeners dispatched by backend
    const eventTypes = [
      "execution_started",
      "task_started",
      "tool_selected",
      "action_started",
      "action_completed",
      "verification_started",
      "verification_completed",
      "approval_required",
      "approval_received",
      "recovery_started",
      "recovery_completed",
      "task_completed",
      "task_failed",
      "execution_paused",
      "execution_resumed",
      "execution_completed",
      "execution_failed",
      "execution_stopped",
      "execution_cancelled",
    ];

    eventTypes.forEach((evtType) => {
      es.addEventListener(evtType, (e: MessageEvent) => {
        try {
          const data: ExecutionEvent = JSON.parse(e.data);
          get().applyEvent(data);
        } catch (err) {
          // ignore parse error
        }
      });
    });

    es.onerror = () => {
      // EventSource automatically retries, set isReconnecting
      set({ isReconnecting: true });
    };
  },

  unsubscribeFromStream: () => {
    const { eventSource } = get();
    if (eventSource) {
      eventSource.close();
      set({ eventSource: null, isStreaming: false, isReconnecting: false });
    }
  },

  pauseExecution: async () => {
    const { execution } = get();
    if (!execution) return;
    try {
      await apiClient.post(`/api/executions/${execution.id}/pause`);
      set((state) => ({
        execution: state.execution ? { ...state.execution, status: "paused" } : null,
      }));
    } catch (err: any) {
      set({ error: err.message || "Failed to pause execution" });
    }
  },

  resumeExecution: async () => {
    const { execution } = get();
    if (!execution) return;
    try {
      await apiClient.post(`/api/executions/${execution.id}/resume`);
      set((state) => ({
        execution: state.execution ? { ...state.execution, status: "running" } : null,
      }));
    } catch (err: any) {
      set({ error: err.message || "Failed to resume execution" });
    }
  },

  cancelExecution: async () => {
    const { execution } = get();
    if (!execution) return;
    try {
      await apiClient.post(`/api/executions/${execution.id}/cancel`);
      set((state) => ({
        execution: state.execution ? { ...state.execution, status: "cancelled" } : null,
      }));
      get().unsubscribeFromStream();
    } catch (err: any) {
      set({ error: err.message || "Failed to cancel execution" });
    }
  },

  decideApproval: async (approvalId: string, decision: "approved" | "rejected", reason?: string) => {
    try {
      await apiClient.post(`/api/approvals/${approvalId}/decide`, {
        decision,
        reason,
        decided_by: "ui",
      });

      set((state) => {
        const updatedApprovals = state.execution?.approvals?.map((a) =>
          a.id === approvalId ? { ...a, status: decision } : a
        ) || [];

        return {
          pendingApproval: null,
          execution: state.execution
            ? {
                ...state.execution,
                status: decision === "approved" ? "running" : "stopped",
                approvals: updatedApprovals,
              }
            : null,
        };
      });
    } catch (err: any) {
      set({ error: err.message || "Failed to submit approval decision" });
      throw err;
    }
  },

  applyEvent: (event: ExecutionEvent) => {
    set((state) => {
      const exists = state.events.some((e) => e.id === event.id || (e.seq > 0 && e.seq === event.seq));
      const newEvents = exists ? state.events : [...state.events, event];

      let execUpdate: Partial<ExecutionDetail> = {};
      let pendingApproval = state.pendingApproval;
      let recoveries = [...state.recoveries];
      let verifications = [...state.verifications];

      switch (event.type) {
        case "execution_started":
          execUpdate = { status: "running", progress: 0.0 };
          break;

        case "task_started":
          execUpdate = {
            current_task_id: event.task_id,
            current_action: `Starting task ${event.task_id}`,
          };
          break;

        case "tool_selected":
          execUpdate = {
            current_action: `Using ${event.tool_id}: ${event.message}`,
          };
          break;

        case "action_started":
          execUpdate = {
            current_action: event.message,
          };
          break;

        case "action_completed":
          execUpdate = {
            current_action: `Completed: ${event.message}`,
          };
          break;

        case "approval_required": {
          execUpdate = { status: "waiting_approval" };
          const p = event.payload || {};
          const approvalItem: Approval = {
            id: p.approval_id || event.id,
            execution_id: state.execution?.id || "",
            task_id: event.task_id || "",
            action: p.action || event.message,
            target: p.target || null,
            content: p.content || {},
            payload_hash: p.payload_hash || "",
            reason: p.reason || "Action requires explicit user confirmation.",
            risk: p.risk || "high",
            consequences: p.consequences || null,
            status: "pending",
            created_at: event.timestamp,
          };
          pendingApproval = approvalItem;
          break;
        }

        case "approval_received":
          pendingApproval = null;
          execUpdate = {
            status: event.payload?.decision === "approved" ? "running" : "stopped",
          };
          break;

        case "recovery_started": {
          const rec: Recovery = {
            id: event.id,
            task_id: event.task_id || "",
            original_tool_id: event.payload?.original_tool_id || "",
            problem: event.payload?.problem || event.message,
            alternative_tool_id: event.payload?.alternative_tool_id || null,
            reason: event.payload?.reason || "",
            status: "pending",
            created_at: event.timestamp,
          };
          recoveries = [...recoveries, rec];
          break;
        }

        case "recovery_completed": {
          const succ = event.payload?.success ?? true;
          recoveries = recoveries.map((r) =>
            r.task_id === event.task_id
              ? { ...r, status: succ ? "succeeded" : "failed" }
              : r
          );
          break;
        }

        case "verification_started":
          break;

        case "verification_completed": {
          const ver: Verification = {
            id: event.id,
            task_id: event.task_id || "",
            criterion: event.payload?.criterion || "System State Verification",
            result: event.payload?.result || (event.payload?.passed ? "passed" : "failed"),
            evidence: event.payload?.evidence || {},
            created_at: event.timestamp,
          };
          verifications = [...verifications, ver];
          break;
        }

        case "task_completed":
          if (event.payload?.progress !== undefined) {
            execUpdate = { progress: Number(event.payload.progress) };
          }
          break;

        case "task_failed":
          execUpdate = { status: "failed" };
          break;

        case "execution_paused":
          execUpdate = { status: "paused" };
          break;

        case "execution_resumed":
          execUpdate = { status: "running" };
          break;

        case "execution_completed": {
          const p = event.payload || {};
          execUpdate = {
            status: "completed",
            progress: 1.0,
            current_action: p.outcome_summary || "Goal evaluation completed.",
            outcome: p.outcome || "COMPLETED",
            evidence_level: p.evidence_level || "GOAL_ACHIEVED",
            outcome_summary: p.outcome_summary || null,
            criteria_evaluations: p.criteria_evaluations || [],
          };
          get().unsubscribeFromStream();
          break;
        }

        case "execution_failed": {
          const p = event.payload || {};
          execUpdate = {
            status: "failed",
            outcome: p.outcome || "FAILED",
            evidence_level: p.evidence_level || "ACTION_REQUESTED",
            outcome_summary: p.outcome_summary || event.message,
            current_action: p.outcome_summary || event.message,
          };
          get().unsubscribeFromStream();
          break;
        }

        case "execution_cancelled":
        case "execution_stopped": {
          const p = event.payload || {};
          execUpdate = {
            status: "cancelled",
            outcome: (event.type === "execution_stopped" ? "STOPPED" : "CANCELLED") as any,
            outcome_summary: p.outcome_summary || "Execution halted by user.",
          };
          get().unsubscribeFromStream();
          break;
        }
      }

      return {
        events: newEvents,
        execution: state.execution ? { ...state.execution, ...execUpdate } : null,
        pendingApproval,
        recoveries,
        verifications,
      };
    });
  },

  reset: () => {
    get().unsubscribeFromStream();
    set({
      execution: null,
      events: [],
      pendingApproval: null,
      recoveries: [],
      verifications: [],
      isStreaming: false,
      isReconnecting: false,
      error: null,
      eventSource: null,
    });
  },
}));
