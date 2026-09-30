import React from "react";
import type { LucideIcon } from "lucide-react";
import {
  Search,
  Globe,
  Navigation,
  CalendarSearch,
  CalendarPlus,
  CalendarMinus,
  Mail,
  MailPlus,
  SendHorizonal,
  MessageSquare,
  CirclePlus,
  FileText,
  File,
  Webhook,
  Plug,
} from "lucide-react";

interface CapabilityDef {
  icon: LucideIcon;
  label: string;
}

const capabilityMap: Record<string, CapabilityDef> = {
  web_search:          { icon: Search,         label: "Web Search" },
  web_read:            { icon: Globe,           label: "Web Read" },
  browser_navigate:    { icon: Navigation,      label: "Browser" },
  calendar_read:       { icon: CalendarSearch,  label: "Calendar Read" },
  calendar_create:     { icon: CalendarPlus,    label: "Calendar Create" },
  calendar_delete:     { icon: CalendarMinus,   label: "Calendar Delete" },
  email_read:          { icon: Mail,            label: "Email Read" },
  email_draft:         { icon: MailPlus,        label: "Email Draft" },
  email_send:          { icon: SendHorizonal,   label: "Email Send" },
  message_send:        { icon: MessageSquare,   label: "Message Send" },
  issue_create:        { icon: CirclePlus,      label: "Issue Create" },
  document_summarize:  { icon: FileText,        label: "Summarize" },
  file_read:           { icon: File,            label: "File Read" },
  api_request:         { icon: Webhook,         label: "API Request" },
  mcp_call:            { icon: Plug,            label: "MCP Call" },
};

interface CapabilityBadgeProps {
  capability_id: string;
}

export const CapabilityBadge: React.FC<CapabilityBadgeProps> = ({
  capability_id,
}) => {
  const def = capabilityMap[capability_id];
  const Icon = def?.icon ?? Plug;
  const label = def?.label ?? capability_id;

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border bg-indigo-50/80 border-indigo-200 text-indigo-700">
      <Icon className="w-3 h-3 shrink-0" />
      {label}
    </span>
  );
};
