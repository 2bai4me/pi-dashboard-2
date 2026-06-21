// SubAgents.tsx - Konfiguration der Sub-Agenten (API-Key/Provider + Rollenbeschreibung pro Rolle)
//
// User-Direktive 18.06.2026: Sub-Agenten sollen konfigurierbar sein mit
// Modell pro Rolle. Standard ist ollama/gemma4:12b.
//
// User-Direktive 20.06.2026: Jede Rolle hat eine editierbare Beschreibung
// (Aufgabe / Worauf achten / Ergebnis-Rückgabe), die als system_prompt gespeichert wird.
//
// User-Direktive 20.06.2026 (Neuordnung): Pro Rolle wird ein API-Key/Provider
// aus der zentralen API-Key-Verwaltung gewählt. Provider-Profile entfallen.

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Save, RefreshCw, AlertCircle, Cpu, FileText, Edit2, X, Key } from "lucide-react";
import { api } from "../api";

interface ProviderCredential {
  id: string;
  provider: string;
  model: string;
  label: string;
  api_key?: string;
  base_url?: string;
  is_active: boolean;
}

interface AgentConfig {
  name: string;
  role_id: string;
  role_type?: string;
  is_subagent: boolean;
  model?: string;
  provider?: string;
  api_key_id?: string | null;
  default_model?: string;
  tools: string[];
  emoji?: string;
  system_prompt?: string;
  description?: string;
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
  const [editApiKeyId, setEditApiKeyId] = useState<string | "">("");
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);
  const [editPromptText, setEditPromptText] = useState("");

  const { data: configs, isLoading, error } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    refetchInterval: 30000,
  });

  const { data: credentialsData } = useQuery({
    queryKey: ["provider-credentials"],
    queryFn: () => api.listProviderCredentials(),
  });

  const credentials: ProviderCredential[] = useMemo(() => {
    return (credentialsData as any)?.items || (Array.isArray(credentialsData) ? credentialsData : []);
  }, [credentialsData]);

  const activeCredentials = useMemo(() => credentials.filter((c) => c.is_active !== false), [credentials]);

  const updateMutation = useMutation({
    mutationFn: ({
      roleName,
      model,
      provider,
      api_key_id,
    }: {
      roleName: string;
      model: string;
      provider?: string;
      api_key_id?: string | null;
    }) => api.subagents.updateModel(roleName, model, provider, api_key_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subagent-configs"] });
      setEditingRole(null);
    },
  });

  const promptMutation = useMutation({
    mutationFn: ({ roleName, systemPrompt }: { roleName: string; systemPrompt: string }) =>
      api.subagents.updatePrompt(roleName, systemPrompt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subagent-configs"] });
      setEditingPrompt(null);
    },
  });

  const startEdit = (config: AgentConfig) => {
    setEditingRole(config.name);
    setEditModel(config.model || "");
    setEditProvider(config.provider || "");
    setEditApiKeyId(config.api_key_id || "");
  };

  const cancelEdit = () => {
    setEditingRole(null);
    setEditModel("");
    setEditProvider("");
    setEditApiKeyId("");
  };

  const selectedCredential = useMemo(() => {
    if (!editApiKeyId) return null;
    return credentials.find((c) => c.id === editApiKeyId) || null;
  }, [editApiKeyId, credentials]);

  const handleCredentialChange = (id: string) => {
    setEditApiKeyId(id);
    const cred = credentials.find((c) => c.id === id);
    if (cred) {
      setEditProvider(cred.provider);
      setEditModel(cred.model);
    }
  };

  const saveEdit = (roleName: string) => {
    if (!editModel) return;
    updateMutation.mutate({
      roleName,
      model: editModel,
      provider: editProvider || undefined,
      api_key_id: editApiKeyId || null,
    });
  };

  const startEditPrompt = (config: AgentConfig) => {
    setEditingPrompt(config.name);
    setEditPromptText(config.system_prompt || "");
  };

  const cancelEditPrompt = () => {
    setEditingPrompt(null);
    setEditPromptText("");
  };

  const savePrompt = (roleName: string) => {
    promptMutation.mutate({ roleName, systemPrompt: editPromptText });
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

  function renderAgentCard(c: AgentConfig, cLevelBadge?: boolean) {
    const isEditingModel = editingRole === c.name;
    const isEditingPrompt = editingPrompt === c.name;
    const linkedCredential = credentials.find((cred) => cred.id === c.api_key_id);
    return (
      <div
        key={c.name}
        style={{
          background: "var(--color-hermes-surface)",
          border: "1px solid var(--color-hermes-border)",
          borderRadius: 8,
          padding: 14,
          opacity: cLevelBadge ? 0.9 : 1,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>{c.emoji || "🤖"}</span>
            <strong style={{ fontSize: 13 }}>{c.name}</strong>
            {cLevelBadge && <span className="badge" style={{ fontSize: 9 }}>C-Level</span>}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {!isEditingModel && (
              <button className="btn btn-sm" onClick={() => startEdit(c)} title="Provider/API-Key ändern">
                <Key size={12} /> Provider
              </button>
            )}
            {!isEditingPrompt && (
              <button className="btn btn-sm" onClick={() => startEditPrompt(c)} title="Rollenbeschreibung bearbeiten">
                <FileText size={12} /> Beschreibung
              </button>
            )}
          </div>
        </div>

        {isEditingModel ? (
          <div>
            <label style={{ display: "block", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
              API-Key / Credential (optional)
            </label>
            <select
              className="select"
              value={editApiKeyId}
              onChange={(e) => handleCredentialChange(e.target.value)}
              style={{ width: "100%", marginBottom: 8 }}
            >
              <option value="">Manuell / Kein API-Key</option>
              {activeCredentials.map((cred) => (
                <option key={cred.id} value={cred.id}>
                  {cred.label} ({cred.provider} / {cred.model})
                </option>
              ))}
              {editApiKeyId && !activeCredentials.find((c) => c.id === editApiKeyId) && (
                <option value={editApiKeyId}>Unbekanntes Credential</option>
              )}
            </select>

            {selectedCredential && (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--color-hermes-text-secondary)",
                  marginBottom: 10,
                  padding: 8,
                  background: "var(--color-hermes-muted)",
                  borderRadius: 4,
                }}
              >
                Provider/Modell werden aus dem API-Key übernommen:
                <br />
                <strong>{selectedCredential.provider}</strong> / <code>{selectedCredential.model}</code>
              </div>
            )}

            <label style={{ display: "block", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
              Modell
            </label>
            <select
              className="select"
              value={editModel}
              onChange={(e) => setEditModel(e.target.value)}
              style={{ width: "100%", marginBottom: 8 }}
              disabled={!!selectedCredential}
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
              disabled={!!selectedCredential}
            />
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="btn btn-sm btn-primary"
                onClick={() => saveEdit(c.name)}
                disabled={updateMutation.isPending}
              >
                <Save size={12} /> Speichern
              </button>
              <button className="btn btn-sm" onClick={cancelEdit}>Abbrechen</button>
            </div>
            {updateMutation.isError && (
              <div style={{ marginTop: 8, color: "var(--color-hermes-danger)", fontSize: 11 }}>
                Fehler: {String(updateMutation.error)}
              </div>
            )}
          </div>
        ) : isEditingPrompt ? (
          <div>
            <label style={{ display: "block", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
              Rollenbeschreibung (Aufgabe / Worauf achten / Ergebnis-Rückgabe)
            </label>
            <textarea
              className="input"
              value={editPromptText}
              onChange={(e) => setEditPromptText(e.target.value)}
              rows={12}
              style={{ width: "100%", marginBottom: 10, fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="btn btn-sm btn-primary"
                onClick={() => savePrompt(c.name)}
                disabled={promptMutation.isPending}
              >
                <Save size={12} /> Speichern
              </button>
              <button className="btn btn-sm" onClick={cancelEditPrompt}>Abbrechen</button>
            </div>
            {promptMutation.isError && (
              <div style={{ marginTop: 8, color: "var(--color-hermes-danger)", fontSize: 11 }}>
                Fehler: {String(promptMutation.error)}
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

            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 10, marginBottom: 4 }}>
              API-Key / Credential
            </div>
            {linkedCredential ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Key size={12} color="var(--color-hermes-accent-blue)" />
                <span style={{ fontSize: 12 }}>{linkedCredential.label}</span>
                <span className="badge" style={{ fontSize: 9 }}>{linkedCredential.provider}</span>
              </div>
            ) : (
              <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>Manuell / Kein API-Key</span>
            )}

            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 10, marginBottom: 4 }}>Tools</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {c.tools.map((tool) => (
                <span key={tool} className="badge" style={{ fontSize: 10 }}>{tool}</span>
              ))}
            </div>

            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 12, marginBottom: 4 }}>
              Rollenbeschreibung
            </div>
            <pre
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                color: "var(--color-hermes-text-secondary)",
                maxHeight: 200,
                overflow: "auto",
                lineHeight: 1.4,
                padding: 8,
                background: "var(--color-hermes-muted)",
                borderRadius: 4,
              }}
            >
              {c.system_prompt || c.description || "(keine Beschreibung hinterlegt)"}
            </pre>
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
          <Bot size={20} />
          Sub-Agent Konfiguration
        </h2>
        <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, margin: 0 }}>
          Jede Rolle hat einen API-Key/Provider und eine editierbare Rollenbeschreibung.
          Änderungen werden sofort in der DB gespeichert und beim nächsten Sub-Agent-Aufruf verwendet.
        </p>
      </div>

      {/* Sub-Agenten Sektion */}
      <h3 style={{ fontSize: 14, marginTop: 20, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        Sub-Agenten (Worker)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: 12 }}>
        {subagents.map((c: AgentConfig) => renderAgentCard(c))}
      </div>

      {/* C-Level Rollen Sektion */}
      <h3 style={{ fontSize: 14, marginTop: 30, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        C-Level Rollen (CIO, CEO-digital, etc.)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: 12 }}>
        {cLevel.map((c: AgentConfig) => renderAgentCard(c, true))}
      </div>
    </div>
  );
}
