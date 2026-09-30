import React from "react";

export type StatusType =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "paused"
  | "waiting_approval"
  | "cancelled"
  | "stopped"
  | "connected"
  | "not_connected"
  | "coming_soon"
  | "error"
  | "succeeded";

interface StatusBadgeProps {
  status: StatusType | string;
  label?: string;
  size?: "sm" | "md";
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, size = "md" }) => {
  const normStatus = status.toLowerCase() as StatusType;

  const config: Record<
    string,
    { bg: string; text: string; dot: string; label: string; pulse?: boolean }
  > = {
    running: {
      bg: "bg-blue-50 border-blue-200",
      text: "text-blue-700",
      dot: "bg-blue-500",
      label: "Running",
      pulse: true,
    },
    completed: {
      bg: "bg-emerald-50 border-emerald-200",
      text: "text-emerald-700",
      dot: "bg-emerald-500",
      label: "Completed",
    },
    succeeded: {
      bg: "bg-emerald-50 border-emerald-200",
      text: "text-emerald-700",
      dot: "bg-emerald-500",
      label: "Succeeded",
    },
    failed: {
      bg: "bg-rose-50 border-rose-200",
      text: "text-rose-700",
      dot: "bg-rose-500",
      label: "Failed",
    },
    paused: {
      bg: "bg-amber-50 border-amber-200",
      text: "text-amber-700",
      dot: "bg-amber-500",
      label: "Paused",
    },
    waiting_approval: {
      bg: "bg-violet-50 border-violet-200",
      text: "text-violet-700",
      dot: "bg-violet-500",
      label: "Needs Approval",
      pulse: true,
    },
    pending: {
      bg: "bg-slate-50 border-slate-200",
      text: "text-slate-600",
      dot: "bg-slate-400",
      label: "Pending",
    },
    cancelled: {
      bg: "bg-slate-50 border-slate-200",
      text: "text-slate-500",
      dot: "bg-slate-400",
      label: "Cancelled",
    },
    stopped: {
      bg: "bg-slate-50 border-slate-200",
      text: "text-slate-500",
      dot: "bg-slate-400",
      label: "Stopped",
    },
    connected: {
      bg: "bg-emerald-50 border-emerald-200",
      text: "text-emerald-700",
      dot: "bg-emerald-500",
      label: "Connected",
    },
    not_connected: {
      bg: "bg-slate-50 border-slate-200",
      text: "text-slate-600",
      dot: "bg-slate-400",
      label: "Not connected",
    },
    coming_soon: {
      bg: "bg-purple-50 border-purple-200",
      text: "text-purple-700",
      dot: "bg-purple-400",
      label: "Coming soon",
    },
    error: {
      bg: "bg-rose-50 border-rose-200",
      text: "text-rose-700",
      dot: "bg-rose-500",
      label: "Error",
    },
  };

  const current = config[normStatus] || {
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    dot: "bg-slate-400",
    label: status,
  };

  const displayText = label || current.label;

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs font-medium";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${current.bg} ${current.text} ${sizeClasses} select-none`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${current.dot} ${
          current.pulse ? "animate-pulse" : ""
        }`}
      />
      <span>{displayText}</span>
    </span>
  );
};
