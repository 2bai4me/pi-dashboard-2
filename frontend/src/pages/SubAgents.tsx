// SubAgents.tsx - Konfiguration der Sub-Agenten (Modell pro Rolle)
//
// User-Direktive 18.06.2026: Sub-Agenten sollen konfigurierbar sein mit
// Modell pro Rolle. Standard ist ollama/gemma4:12b. User kann das Modell
// pro Rolle aendern (z.B. fuer Tests oder spezielle Anforderungen).

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Save, RefreshCw, Check, AlertCircle, Cpu } from "lucide-react";
import { api } from "../api";

interface AgentConfig {
  name: string;
  role_id: string;
  role_type?: string;
  is_subagent: boolean;
  model?: string;
  provider?: string;
  default_model?: string;
  tools: string[];
  emoji?: string;
}

const PRESET_MODELS = [
  { value: "ollama/gemma4:12b", label: "gemma4:12b (lokal, Standard)" },
  { value: "ollama/qwen3:4b", label: "qwen3:4b (lokal, klein)" },
  { value: "ollama/llama3.1:8b", label: "llama3.1:8b (lokal, mittel)" },
  { value: "minimax-m3", label: "minimax-m3 (cloud)" },
];

export default function SubAgents() {
  const queryClient = useQueryClient();
  const [editingRole, setEditingRole] = useState<string | null>(null);
  const [editModel, setEditModel] = useState("");
  const [editProvider, setEditProvider] = useState("");

  const { data: configs, isLoading, error } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    refetchInterval: 30000,
  });

  const updateMutation = useMutation({
    mutationFn: ({ roleName, model, provider }: { roleName: string; model: string; provider?: string }) =>
      api.subagents.updateModel(roleName, model, provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subagent-configs"] });
      setEditingRole(null);
    },
  });

  const startEdit = (config: AgentConfig) => {
    setEditingRole(config.name);
    setEditModel(config.model || "");
    setEditProvider(config.provider || "");
  };

  const cancelEdit = () => {
    setEditingRole(null);
    setEditModel("");
    setEditProvider("");
  };

  const saveEdit = (roleName: string) => {
    if (!editModel) return;
    updateMutation.mutate({ roleName, model: editModel, provider: editProvider || undefined });
  };

  if (isLoading) {
    return (
      <div style={{ padding: 20, color: "var(--color-hermes-text-secondary)" }}>
        Lade Sub-Agent-Konfigurationen...
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ padding: 20, color: "var(--color-hermes-danger)" }}>
        <AlertCircle size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
        Fehler beim Laden: {String(error)}
      </div>
    );
  }

  const subagents = (configs || []).filter((c: AgentConfig) => c.is_subagent);
  const cLevel = (configs || []).filter((c: AgentConfig) => !c.is_subagent);

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
          <Bot size={20} />
          Sub-Agent Konfiguration
        </h2>
        <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, margin: 0 }}>
          Jede Rolle hat ein konfiguriertes Modell. Standard fuer Sub-Agenten (pi-coder, pi-tester, pi-reviewer, pi-fixer): <code>ollama/gemma4:12b</code>.
          Aenderungen werden sofort in der DB gespeichert und beim naechsten Sub-Agent-Aufruf verwendet.
        </p>
      </div>

      {/* Sub-Agenten Sektion */}
      <h3 style={{ fontSize: 14, marginTop: 20, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        Sub-Agenten (Worker)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 12 }}>
        {subagents.map((c: AgentConfig) => {
          const isEditing = editingRole === c.name;
          return (
            <div
              key={c.name}
              style={{
                background: "var(--color-hermes-surface)",
                border: "1px solid var(--color-hermes-border)",
                borderRadius: 8,
                padding: 14,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 18 }}>{c.emoji || "🤖"}</span>
                  <strong style={{ fontSize: 13 }}>{c.name}</strong>
                </div>
                {!isEditing && (
                  <button className="btn btn-sm" onClick={() => startEdit(c)}>
                    <Cpu size={12} /> Aendern
                  </button>
                )}
              </div>

              {isEditing ? (
                <div>
                  <label style={{ display: "block", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                    Modell
                  </label>
                  <select
                    className="select"
                    value={editModel}
                    onChange={(e) => setEditModel(e.target.value)}
                    style={{ width: "100%", marginBottom: 8 }}
                  >
                    {PRESET_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                    {!PRESET_MODELS.find((m) => m.value === editModel) && editModel && (
                      <option value={editModel}>{editModel}</option>
                    )}
                  </select>
                  <label style={{ display: "block", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                    Provider (optional, wird automatisch erkannt)
                  </label>
                  <input
                    className="input"
                    value={editProvider}
                    onChange={(e) => setEditProvider(e.target.value)}
                    placeholder="ollama / minimax-direct / ..."
                    style={{ width: "100%", marginBottom: 10 }}
                  />
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => saveEdit(c.name)}
                      disabled={updateMutation.isPending}
                    >
                      <Save size={12} /> Speichern
                    </button>
                    <button className="btn btn-sm" onClick={cancelEdit}>
                      Abbrechen
                    </button>
                  </div>
                  {updateMutation.isError && (
                    <div style={{ marginTop: 8, color: "var(--color-hermes-danger)", fontSize: 11 }}>
                      Fehler: {String(updateMutation.error)}
                    </div>
                  )}
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>Modell</div>
                  <code style={{ fontSize: 12, background: "var(--color-hermes-bg)", padding: "2px 6px", borderRadius: 3 }}>
                    {c.model || "(nicht gesetzt)"}
                  </code>
                  {c.default_model && c.model !== c.default_model && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                      Standard: <code>{c.default_model}</code>
                    </div>
                  )}

                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 10, marginBottom: 4 }}>Provider</div>
                  <code style={{ fontSize: 12 }}>{c.provider || "—"}</code>

                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 10, marginBottom: 4 }}>Tools</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {c.tools.map((tool) => (
                      <span key={tool} className="badge" style={{ fontSize: 10 }}>{tool}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* C-Level Rollen Sektion */}
      <h3 style={{ fontSize: 14, marginTop: 30, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        C-Level Rollen (CIO, CEO-digital, etc.)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 12 }}>
        {cLevel.map((c: AgentConfig) => {
          const isEditing = editingRole === c.name;
          return (
            <div
              key={c.name}
              style={{
                background: "var(--color-hermes-surface)",
                border: "1px solid var(--color-hermes-border)",
                borderRadius: 8,
                padding: 14,
                opacity: 0.85,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 18 }}>{c.emoji || "👤"}</span>
                  <strong style={{ fontSize: 13 }}>{c.name}</strong>
                  <span className="badge" style={{ fontSize: 9 }}>C-Level</span>
                </div>
                {!isEditing && (
                  <button className="btn btn-sm" onClick={() => startEdit(c)}>
                    <Cpu size={12} /> Aendern
                  </button>
                )}
              </div>

              {isEditing ? (
                <div>
                  <select className="select" value={editModel} onChange={(e) => setEditModel(e.target.value)} style={{ width: "100%", marginBottom: 8 }}>
                    {PRESET_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-sm btn-primary" onClick={() => saveEdit(c.name)} disabled={updateMutation.isPending}>
                      <Save size={12} /> Speichern
                    </button>
                    <button className="btn btn-sm" onClick={cancelEdit}>Abbrechen</button>
                  </div>
                </div>
              ) : (
                <div>
                  <code style={{ fontSize: 12, background: "var(--color-hermes-bg)", padding: "2px 6px", borderRadius: 3 }}>
                    {c.model || "(nicht gesetzt)"}
                  </code>
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{c.provider}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
