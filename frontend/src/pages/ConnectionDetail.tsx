import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, CheckCircle, AlertTriangle, Clock, RefreshCw, Unplug, ExternalLink } from "lucide-react";
import { useConnectionStore } from "../stores/connectionStore";
import type { AppDefinition, HealthCheckResult } from "../stores/connectionStore";
import type { Connection } from "../types";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Skeleton } from "../components/ui/Skeleton";
import { Toggle } from "../components/ui/Toggle";
import { useUIStore } from "../stores/uiStore";

function StatusIcon({ status }: { status: string }) {
  if (status === "connected") return <CheckCircle size={16} className="text-green-500" />;
  if (status === "needs_reconnection") return <AlertTriangle size={16} className="text-red-500" />;
  return <Clock size={16} className="text-slate-400" />;
}

export default function ConnectionDetail() {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const { catalog, connections, fetchCatalog, fetchConnections, disconnectApp, togglePermission, testConnectionHealth } = useConnectionStore();
  const { addToast } = useUIStore();

  const [healthResult, setHealthResult] = useState<HealthCheckResult | null>(null);
  const [testingHealth, setTestingHealth] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    if (catalog.length === 0) fetchCatalog();
    if (connections.length === 0) fetchConnections();
  }, [catalog.length, connections.length, fetchCatalog, fetchConnections]);

  const appDef: AppDefinition | undefined = catalog.find((a) => a.app_id === appId);
  const conn: Connection | undefined = connections.find((c) => c.app_id === appId);

  if (catalog.length === 0 || connections.length === 0) {
    return (
      <div className="p-6 max-w-2xl mx-auto space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  }

  if (!appDef) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <Button variant="ghost" onClick={() => navigate("/connections")}>
          <ArrowLeft size={16} className="mr-1" /> Back
        </Button>
        <div className="mt-6 text-slate-500">App not found in catalog.</div>
      </div>
    );
  }

  async function handleTestHealth() {
    if (!conn) return;
    setTestingHealth(true);
    try {
      const result = await testConnectionHealth(conn.id);
      setHealthResult(result);
      addToast({
        type: result.status === "healthy" ? "success" : "warning",
        title: result.status === "healthy" ? "Connection healthy" : "Connection issue",
        message: result.message,
      });
    } catch {
      addToast({ type: "error", title: "Test failed", message: "Could not reach health endpoint." });
    } finally {
      setTestingHealth(false);
    }
  }

  async function handleDisconnect() {
    if (!conn) return;
    if (!confirm(`Disconnect ${appDef.name}? Relay will stop accessing this service immediately.`)) return;
    setDisconnecting(true);
    try {
      await disconnectApp(conn.id);
      addToast({ type: "success", title: "Disconnected", message: `${appDef.name} has been disconnected.` });
      navigate("/connections");
    } catch {
      addToast({ type: "error", title: "Error", message: "Could not disconnect." });
      setDisconnecting(false);
    }
  }

  const connectionStatus = conn?.status ?? "not_connected";

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      {/* Back nav */}
      <button
        onClick={() => navigate("/connections")}
        className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 transition-colors"
      >
        <ArrowLeft size={16} /> Back to Connections
      </button>

      {/* App header */}
      <div className="flex items-start gap-4">
        <div className="text-5xl">{appDef.icon_emoji}</div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold text-slate-900">{appDef.name}</h1>
            <Badge label={appDef.category} color="slate" size="sm" />
            {!appDef.available && <Badge label="Coming soon" color="amber" size="sm" />}
          </div>
          <p className="text-slate-500 text-sm">{appDef.description}</p>
          {appDef.docs_url && (
            <a href={appDef.docs_url} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 mt-1">
              Documentation <ExternalLink size={10} />
            </a>
          )}
        </div>
      </div>

      {/* Connection status card */}
      <Card className="p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Connection Status</h2>
        <div className="flex items-center gap-2 mb-3">
          <StatusIcon status={connectionStatus} />
          <span className="font-medium capitalize">{connectionStatus.replace(/_/g, " ")}</span>
          {conn?.auth_type && (
            <Badge label={conn.auth_type.replace("_", " ")} color="indigo" size="sm" />
          )}
        </div>

        {/* Health check result */}
        {healthResult && (
          <div className={`rounded-lg p-3 mb-3 text-sm ${
            healthResult.status === "healthy"
              ? "bg-green-50 border border-green-200 text-green-800"
              : "bg-amber-50 border border-amber-200 text-amber-800"
          }`}>
            <strong>{healthResult.status === "healthy" ? "✓ Healthy" : "⚠ Issue detected"}</strong>
            <span className="ml-2">{healthResult.message}</span>
            <span className="text-xs ml-2 opacity-60">
              {new Date(healthResult.checked_at).toLocaleTimeString()}
            </span>
          </div>
        )}

        <div className="flex gap-2 flex-wrap">
          {conn && connectionStatus !== "not_connected" && (
            <Button size="sm" variant="outline" onClick={handleTestHealth} isLoading={testingHealth}>
              <RefreshCw size={12} className="mr-1" /> Test Connection
            </Button>
          )}
          {conn && connectionStatus !== "not_connected" && (
            <Button size="sm" variant="ghost"
              className="text-red-600 hover:text-red-700"
              onClick={handleDisconnect}
              isLoading={disconnecting}>
              <Unplug size={12} className="mr-1" /> Disconnect
            </Button>
          )}
          {(!conn || connectionStatus === "not_connected") && (
            <Button size="sm" onClick={() => navigate("/connections")}>
              Connect via Connections page
            </Button>
          )}
        </div>
      </Card>

      {/* Capabilities */}
      <Card className="p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Capabilities</h2>
        {appDef.capabilities.length === 0 ? (
          <p className="text-sm text-slate-400">No capabilities — this integration is coming soon.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {appDef.capabilities.map((cap) => (
              <Badge key={cap} label={cap.replace(/_/g, " ")} color="blue" size="sm" />
            ))}
          </div>
        )}
      </Card>

      {/* Permissions */}
      {conn && conn.permissions && conn.permissions.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Permissions</h2>
          <div className="space-y-2">
            {conn.permissions.map((perm) => (
              <div key={perm.id} className="flex items-center justify-between py-1">
                <div>
                  <span className="text-sm font-medium text-slate-800">{perm.label}</span>
                  {perm.is_sensitive && (
                    <Badge label="sensitive" color="amber" size="sm" />
                  )}
                </div>
                <Toggle
                  checked={perm.is_granted}
                  onChange={(val) => togglePermission(conn.id, perm.key, val)}
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Setup info */}
      <Card className="p-4 bg-slate-50">
        <h2 className="text-sm font-semibold text-slate-700 mb-2">Setup Instructions</h2>
        <p className="text-sm text-slate-600">{appDef.auth_instructions}</p>
        <div className="mt-2 flex gap-2">
          <Badge label={`Auth: ${appDef.auth_label}`} color="slate" size="sm" />
          <Badge label={`Risk: ${appDef.risk_profile}`}
            color={appDef.risk_profile === "high" ? "red" : appDef.risk_profile === "medium" ? "amber" : "green"}
            size="sm" />
        </div>
      </Card>
    </div>
  );
}
