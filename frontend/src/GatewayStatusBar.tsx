import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Settings, Volume2 } from "lucide-react";
import { api } from "./api";
import { useTTSContext } from "./TTSContext";
import { TTSControl } from "./TTSControl";

function SettingsModal({ onClose }: { onClose: () => void }) {
  const tts = useTTSContext();
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 460 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
            <Settings size={16} /> Einstellungen
          </h3>
          <button className="btn btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ borderTop: "1px solid var(--color-hermes-border)", paddingTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
            <Volume2 size={14} /> Sprachausgabe (TTS)
          </div>
          <TTSControl tts={tts} />
        </div>

        <div style={{ marginTop: 14, fontSize: 12, color: "var(--color-hermes-text-secondary)", lineHeight: 1.6 }}>
          <strong>Modus:</strong><br />
          🔇 Aus — Keine Sprachausgabe<br />
          👆 Klick — Text durch Klick vorlesen<br />
          🔄 Auto — Automatisch vorlesen (in Vorbereitung)
        </div>
      </div>
    </div>
  );
}

export function GatewayStatusBar() {
  const [showSettings, setShowSettings] = useState(() => {
    if (typeof window !== "undefined") {
      return new URLSearchParams(window.location.hash.split("?")[1] || "").get("settings") === "open"
    }
    return false
  });
  const { data: status, refetch } = useQuery({
    queryKey: ["gateway-status"],
    queryFn: () => api.getGatewayStatus(),
    refetchInterval: 15000,
  });
  const queryClient = useQueryClient();

  const restartMut = useMutation({
    mutationFn: () => api.restartOllama(),
    onSuccess: () => setTimeout(() => refetch(), 3000),
  });

  const services = [
    { name: "Dashboard", key: "dashboard" },
    { name: "Ollama", key: "ollama" },
    { name: "PI Agent", key: "pi" },
  ];

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "4px 16px",
      background: "var(--color-hermes-surface)",
      borderBottom: "1px solid var(--color-hermes-border)",
      fontSize: 11,
      color: "var(--color-hermes-text-secondary)",
      minHeight: 28,
      flexShrink: 0,
    }}>
      {/* Status Dots */}
      {services.map((svc) => {
        const svcStatus = status?.[svc.key];
        const isRunning = svcStatus?.running;
        const hasError = !!svcStatus?.error;
        return (
          <div key={svc.key} style={{ display: "flex", alignItems: "center", gap: 4 }} title={isRunning ? `${svc.name}: running` : `${svc.name}: ${svcStatus?.error || "stopped"}`}>
            {isRunning ? (
              <CheckCircle size={10} color="var(--color-hermes-accent)" style={{ flexShrink: 0 }} />
            ) : hasError ? (
              <AlertTriangle size={10} color="var(--color-hermes-danger)" style={{ flexShrink: 0 }} />
            ) : (
              <XCircle size={10} color="var(--color-hermes-text-secondary)" style={{ flexShrink: 0 }} />
            )}
            <span>{svc.name}</span>
          </div>
        );
      })}

      {/* Ollama Models Badge */}
      {status?.ollama?.running && (
        <span className="badge badge-green" style={{ fontSize: 9, padding: "1px 6px" }}>
          {status.ollama.model_count} models
        </span>
      )}
      {status?.ollama?.running && status.ollama.models?.length > 0 && (
        <span style={{ fontSize: 10, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {status.ollama.models.join(", ")}
        </span>
      )}

      {/* PI Version */}
      {status?.pi?.version && (
        <span style={{ color: "var(--color-hermes-accent-blue)", fontSize: 10 }}>
          v{status.pi.version}
        </span>
      )}

      <div style={{ flex: 1 }} />

      {/* Restart Ollama */}
      <button
        className="btn"
        style={{ padding: "2px 8px", fontSize: 10, display: "flex", alignItems: "center", gap: 4 }}
        onClick={() => restartMut.mutate()}
        disabled={restartMut.isPending}
        title="Restart Ollama"
      >
        <RefreshCw size={10} className={restartMut.isPending ? "spin" : ""} />
        Restart Ollama
      </button>

      {/* Refresh */}
      <button
        className="btn"
        style={{ padding: "2px 8px", fontSize: 10 }}
        onClick={() => refetch()}
        title="Refresh status"
      >
        <RefreshCw size={10} />
      </button>

      {/* Settings Gear */}
      <button
        className="btn"
        style={{ padding: "2px 6px", fontSize: 10 }}
        onClick={() => setShowSettings(true)}
        title="Einstellungen"
      >
        <Settings size={12} />
      </button>

      {/* Settings Modal */}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
