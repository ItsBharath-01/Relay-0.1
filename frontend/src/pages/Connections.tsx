import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plug, RefreshCw, Zap, CheckCircle, AlertTriangle, Clock, ExternalLink } from "lucide-react";
import { useConnectionStore } from "../stores/connectionStore";
import type { AppDefinition } from "../stores/connectionStore";
import type { Connection } from "../types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { MCPRegistrationModal } from "../components/ui/MCPRegistrationModal";
import { useUIStore } from "../stores/uiStore";

// ── Helpers ──────────────────────────────────────────────────────────────────

type FilterTab = "all" | "connected" | "available" | "coming_soon";

const CATEGORY_LABELS: Record<string, string> = {
  productivity: "Productivity",
  communication: "Communication",
  developer: "Developer",
  browser: "Browser",
  local: "Local",
  api: "APIs",
};

function statusColor(status: string) {
  if (status === "connected") return "green";
  if (status === "needs_reconnection") return "red";
  if (status === "not_connected") return "slate";
  return "amber";
}

function StatusIcon({ status }: { status: string }) {
  if (status === "connected") return <CheckCircle size={14} className="text-green-500" />;
  if (status === "needs_reconnection") return <AlertTriangle size={14} className="text-red-500" />;
  return <Clock size={14} className="text-slate-400" />;
}

// ── Connected App Card ────────────────────────────────────────────────────────

function ConnectedCard({ conn, appDef }: { conn: Connection; appDef: AppDefinition | undefined }) {
  const { disconnectApp, testConnectionHealth } = useConnectionStore();
  const { addToast } = useUIStore();
  const navigate = useNavigate();
  const [testing, setTesting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const name = appDef?.name ?? conn.app_id;
  const emoji = appDef?.icon_emoji ?? "🔌";

  async function handleTest() {
    setTesting(true);
    try {
      const result = await testConnectionHealth(conn.id);
      addToast({
        type: result.status === "healthy" ? "success" : "error",
        title: result.status === "healthy" ? "Connection healthy" : "Connection issue",
        message: result.message,
      });
    } catch {
      addToast({ type: "error", title: "Test failed", message: "Could not reach health endpoint." });
    } finally {
      setTesting(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm(`Disconnect ${name}? Relay will no longer be able to access this service.`)) return;
    setDisconnecting(true);
    try {
      await disconnectApp(conn.id);
      addToast({ type: "success", title: "Disconnected", message: `${name} has been disconnected.` });
    } catch {
      addToast({ type: "error", title: "Error", message: "Could not disconnect." });
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <Card className="flex items-start gap-3 p-4">
      <div className="text-2xl mt-0.5">{emoji}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-slate-900">{name}</span>
          <StatusIcon status={conn.status} />
          <Badge label={conn.status.replace("_", " ")} color={statusColor(conn.status) as never} size="sm" />
        </div>
        {appDef && (
          <div className="flex flex-wrap gap-1 mb-2">
            {appDef.capabilities.map((cap) => (
              <Badge key={cap} label={cap.replace("_", " ")} color="blue" size="sm" />
            ))}
          </div>
        )}
        {conn.discovered_tools && conn.discovered_tools.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2 items-center">
            <Badge label={`${conn.discovered_tools.length} MCP tools`} color="indigo" size="sm" />
            {conn.discovered_tools.slice(0, 3).map((t) => (
              <Badge key={t.name} label={t.name} color="slate" size="sm" />
            ))}
            {conn.discovered_tools.length > 3 && (
              <span className="text-xs text-slate-400">+{conn.discovered_tools.length - 3} more</span>
            )}
          </div>
        )}
        <div className="flex gap-2 flex-wrap mt-2">
          <Button size="sm" variant="outline" onClick={handleTest} isLoading={testing}>
            <RefreshCw size={12} className="mr-1" /> Test
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate(`/connections/${conn.app_id}`)}>
            <ExternalLink size={12} className="mr-1" /> Manage
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDisconnect} isLoading={disconnecting}
            className="text-red-600 hover:text-red-700">
            Disconnect
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ── Inline Connect Form ────────────────────────────────────────────────────────

function ConnectForm({ app, onDone }: { app: AppDefinition; onDone: () => void }) {
  const { initConnection, connectWithToken } = useConnectionStore();
  const { addToast } = useUIStore();
  const [token, setToken] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const connId = await initConnection(app.app_id);
      const value = app.connection_type === "url_config" || app.connection_type === "mcp" ? url : token;
      await connectWithToken(connId, value);
      addToast({ type: "success", title: "Connected!", message: `${app.name} is now connected.` });
      onDone();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Connection failed";
      addToast({ type: "error", title: "Connection failed", message: msg });
    } finally {
      setLoading(false);
    }
  }

  if (app.connection_type === "oauth") {
    return (
      <div className="mt-3 rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
        <strong>OAuth required.</strong> {app.auth_instructions} Live OAuth is available when Google Cloud credentials are configured on the server.
      </div>
    );
  }

  if (app.connection_type === "local") {
    async function handleLocal() {
      setLoading(true);
      try {
        await initConnection(app.app_id);
        addToast({ type: "success", title: "Enabled", message: `${app.name} is ready.` });
        onDone();
      } catch {
        addToast({ type: "error", title: "Error", message: "Could not enable local tool." });
      } finally {
        setLoading(false);
      }
    }
    return (
      <div className="mt-3">
        <p className="text-xs text-slate-500 mb-2">{app.auth_instructions}</p>
        <Button size="sm" onClick={handleLocal} isLoading={loading}>Enable</Button>
      </div>
    );
  }

  const [mcpModalOpen, setMcpModalOpen] = useState(false);

  if (app.connection_type === "mcp") {
    return (
      <div className="mt-3">
        <p className="text-xs text-slate-500 mb-2">{app.auth_instructions}</p>
        <Button size="sm" onClick={() => setMcpModalOpen(true)}>Configure MCP Server</Button>
        <MCPRegistrationModal isOpen={mcpModalOpen} onClose={() => { setMcpModalOpen(false); onDone(); }} />
      </div>
    );
  }

  const isUrlBased = app.connection_type === "url_config";

  return (
    <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
      <Input
        type={isUrlBased ? "url" : "password"}
        placeholder={isUrlBased ? "https://..." : app.auth_label}
        value={isUrlBased ? url : token}
        onChange={(e) => isUrlBased ? setUrl(e.target.value) : setToken(e.target.value)}
        className="flex-1 text-sm"
        required
      />
      <Button type="submit" size="sm" isLoading={loading}>Connect</Button>
    </form>
  );
}

// ── Catalog App Card ──────────────────────────────────────────────────────────

function CatalogCard({ app }: { app: AppDefinition }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <div className="text-2xl mt-0.5">{app.icon_emoji}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-slate-900">{app.name}</span>
            <Badge label={app.connection_type.replace("_", " ")} color="indigo" size="sm" />
          </div>
          <p className="text-xs text-slate-500 mb-2">{app.description}</p>
          <div className="flex flex-wrap gap-1 mb-2">
            {app.capabilities.map((cap) => (
              <Badge key={cap} label={cap.replace("_", " ")} color="blue" size="sm" />
            ))}
          </div>
          {!expanded && (
            <Button size="sm" variant="outline" onClick={() => setExpanded(true)}>
              <Plug size={12} className="mr-1" /> Connect
            </Button>
          )}
          {expanded && <ConnectForm app={app} onDone={() => setExpanded(false)} />}
        </div>
      </div>
    </Card>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Connections() {
  const { connections, catalog, isLoading, catalogLoading, fetchConnections, fetchCatalog } = useConnectionStore();
  const [filter, setFilter] = useState<FilterTab>("all");
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");

  useEffect(() => {
    fetchConnections();
    fetchCatalog();
  }, [fetchConnections, fetchCatalog]);

  const connectedAppIds = new Set(
    connections.filter((c) => c.status !== "not_connected").map((c) => c.app_id)
  );

  // Build lookup: app_id → AppDefinition
  const catalogMap = new Map(catalog.map((a) => [a.app_id, a]));

  // Active connections (user has a row with non-empty/not_connected status)
  const activeConnections = connections.filter((c) => c.status !== "not_connected");

  // Available catalog apps the user hasn't connected yet
  const availableCatalog = catalog.filter(
    (a) => a.available && !connectedAppIds.has(a.app_id)
  );

  // Coming-soon
  const comingSoon = catalog.filter((a) => !a.available);

  // Search filter helper
  function matchesSearch(name: string, description: string) {
    if (!search) return true;
    const q = search.toLowerCase();
    return name.toLowerCase().includes(q) || description.toLowerCase().includes(q);
  }

  const categories = ["all", ...Array.from(new Set(availableCatalog.map((a) => a.category)))];

  const filteredAvailable = availableCatalog
    .filter((a) => matchesSearch(a.name, a.description))
    .filter((a) => activeCategory === "all" || a.category === activeCategory);

  if (isLoading && catalogLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Connections</h1>
        <p className="text-slate-500 text-sm mt-1">
          Connect apps and services so Relay can take real actions on your behalf.
        </p>
      </div>

      {/* Search + Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Input
          placeholder="Search integrations…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
        />
        <div className="flex gap-1">
          {(["all", "connected", "available", "coming_soon"] as FilterTab[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f
                  ? "bg-violet-100 text-violet-700"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {f === "coming_soon" ? "Coming soon" : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Section 1 — Connected */}
      {(filter === "all" || filter === "connected") && (
        <section>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3 flex items-center gap-2">
            <CheckCircle size={14} className="text-green-500" />
            Connected ({activeConnections.filter((c) => matchesSearch(catalogMap.get(c.app_id)?.name ?? c.app_id, "")).length})
          </h2>
          {activeConnections.length === 0 ? (
            <EmptyState
              icon={<Plug size={32} className="text-slate-300" />}
              title="No apps connected"
              description="Connect apps below so Relay can take real actions."
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {activeConnections
                .filter((c) => matchesSearch(catalogMap.get(c.app_id)?.name ?? c.app_id, ""))
                .map((conn) => (
                  <ConnectedCard
                    key={conn.id}
                    conn={conn}
                    appDef={catalogMap.get(conn.app_id)}
                  />
                ))}
            </div>
          )}
        </section>
      )}

      {/* Section 2 — Available */}
      {(filter === "all" || filter === "available") && (
        <section>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3 flex items-center gap-2">
            <Zap size={14} className="text-blue-500" />
            Available Integrations
          </h2>

          {/* Category tabs */}
          <div className="flex flex-wrap gap-1 mb-4">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  activeCategory === cat
                    ? "bg-blue-600 text-white border-blue-600"
                    : "border-slate-200 text-slate-600 hover:border-slate-400"
                }`}
              >
                {cat === "all" ? "All" : CATEGORY_LABELS[cat] ?? cat}
              </button>
            ))}
          </div>

          {filteredAvailable.length === 0 ? (
            <EmptyState
              icon={<Plug size={32} className="text-slate-300" />}
              title="No integrations available"
              description={search ? "Try a different search term." : "All available integrations are already connected."}
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {filteredAvailable.map((app) => (
                <CatalogCard key={app.app_id} app={app} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Section 3 — Coming soon */}
      {(filter === "all" || filter === "coming_soon") && comingSoon.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">
            Coming Soon
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 opacity-60">
            {comingSoon
              .filter((a) => matchesSearch(a.name, a.description))
              .map((app) => (
                <Card key={app.app_id} className="p-4 cursor-not-allowed">
                  <div className="flex items-start gap-3">
                    <div className="text-2xl mt-0.5 grayscale">{app.icon_emoji}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium text-slate-700">{app.name}</span>
                        <Badge label="Coming soon" color="slate" size="sm" />
                      </div>
                      <p className="text-xs text-slate-400">{app.description}</p>
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        </section>
      )}
    </div>
  );
}
