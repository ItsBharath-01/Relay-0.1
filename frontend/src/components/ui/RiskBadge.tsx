import React from "react";

interface RiskBadgeProps {
  risk: "low" | "medium" | "high" | "critical";
}

const riskStyles: Record<RiskBadgeProps["risk"], string> = {
  low:      "bg-green-50  border-green-300  text-green-700",
  medium:   "bg-amber-50  border-amber-300  text-amber-700",
  high:     "bg-orange-50 border-orange-400 text-orange-700",
  critical: "bg-red-50    border-red-400    text-red-700",
};

const riskLabel: Record<RiskBadgeProps["risk"], string> = {
  low:      "Low",
  medium:   "Medium",
  high:     "High",
  critical: "Critical",
};

export const RiskBadge: React.FC<RiskBadgeProps> = ({ risk }) => (
  <span
    className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full border ${riskStyles[risk]}`}
  >
    {riskLabel[risk]}
  </span>
);
