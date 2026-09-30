import React from "react";
import { useUIStore } from "../../stores/uiStore";

const statusConfig = {
  ready: {
    dot: "bg-green-500",
    text: "text-green-700",
    label: "Ready",
  },
  unavailable: {
    dot: "bg-amber-400",
    text: "text-amber-700",
    label: "Unavailable",
  },
  model_missing: {
    dot: "bg-amber-400",
    text: "text-amber-700",
    label: "Model Missing",
  },
  backend_unavailable: {
    dot: "bg-red-500",
    text: "text-red-700",
    label: "Backend Down",
  },
} as const;

export const LLMStatusIndicator: React.FC = () => {
  const { llmHealth, isCheckingLLM, checkLLMHealth } = useUIStore((s) => ({
    llmHealth: s.llmHealth,
    isCheckingLLM: s.isCheckingLLM,
    checkLLMHealth: s.checkLLMHealth,
  }));

  if (llmHealth === null) {
    return (
      <button
        onClick={() => void checkLLMHealth()}
        disabled={isCheckingLLM}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-500 text-xs font-medium hover:bg-slate-100 transition-colors disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-primary-500"
        title="Check LLM status"
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            isCheckingLLM ? "bg-slate-400 animate-pulse" : "bg-slate-400"
          }`}
        />
        {isCheckingLLM ? "Checking…" : "LLM Status"}
      </button>
    );
  }

  const cfg =
    statusConfig[llmHealth.status as keyof typeof statusConfig] ?? statusConfig.unavailable;

  return (
    <button
      onClick={() => void checkLLMHealth()}
      disabled={isCheckingLLM}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border bg-white text-xs font-medium hover:opacity-80 transition-opacity disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-primary-500 border-slate-200 ${cfg.text}`}
      title={`Model: ${llmHealth.model ?? "unknown"}${
        llmHealth.error ? ` — ${llmHealth.error}` : ""
      }`}
    >
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot} ${
          llmHealth.status === "ready" ? "animate-pulse" : ""
        }`}
      />
      <span>{cfg.label}</span>
      {llmHealth.model && (
        <span className="text-slate-400 font-normal truncate max-w-[120px]">
          · {llmHealth.model}
        </span>
      )}
    </button>
  );
};
