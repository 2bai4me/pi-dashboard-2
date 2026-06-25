// SubAgents.tsx - Konfiguration der Sub-Agenten
//
// Vereinfachtes UI (User-Direktive 22.06.2026):
//   * Pro Karte genau ein "Bearbeiten"-Button
//   * Alle Felder koennen gleichzeitig editiert und in einem Aufruf gespeichert werden
//   * "Abbrechen" macht alle Aenderungen rueckgaengig

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Save, RefreshCw, AlertCircle, FileText, X, Key, Pencil, Workflow, Server, Trash2 } from "lucide-react";
import { api } from "../api";
import { useAvailableModels } from "../hooks/useAvailableModels";
import { PageId } from "../components/PageId";
import { PAGE_IDS } from "../pageIds";

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
  display_name?: string | null;
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
  assigned_sop_id?: string | null;
}

interface EditState {
  display_name: string;
  sop_id: string;
  model: string;
  provider: string;
  api_key_id: string;
  system_prompt: string;
}

function emptyEdit(): EditState {
  return {
    display_name: "",
    sop_id: "",
    model: "",
    provider: "",
    api_key_id: "",
    system_prompt: "",
  };
}

function buildEdit(c: AgentConfig): EditState {
  // BUG-FIX 24.06.2026: Wenn das model-Feld in der DB ein Credential-ID-Praefix hat
  // (z.B. "d3ab3944:minimax-m3" durch einen frueheren Bug), beim Bearbeiten das reine
  // Model ableiten, damit das Dropdown den richtigen Eintrag anzeigt.
  let model = c.model || "";
  let provider = c.provider || "";
  if (model.includes(":")) {
    // Format "<credential_id>:<model>" -> nur model behalten
    const parts = model.split(":", 1);
    model = model.substring(parts[0].length + 1);
  }
  return {
    display_name: c.display_name || "",
    sop_id: c.assigned_sop_id || "",
    model: model,
    provider: provider,
    api_key_id: c.api_key_id || "",
    system_prompt: c.system_prompt || "",
  };
}

export default function SubAgents() {
  const queryClient = useQueryClient();
  const [editingRole, setEditingRole] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState>(emptyEdit());
  // === FIX 23.06.2026 (BUG 488cff11bbe8): User-Feedback bei Save-Erfolg/-Fehler ===
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: configs, isLoading, error } = useQuery({
    queryKey: ["subagent-configs"],
    queryFn: () => api.subagents.listConfigs(),
    refetchInterval: 30000,
  });

  const { data: credentialsData } = useQuery({
    queryKey: ["provider-credentials"],
    queryFn: () => api.listProviderCredentials(),
  });

  const { data: sopsData } = useQuery({
    queryKey: ["sops"],
    queryFn: () => api.listSops(),
  });

  const credentials: ProviderCredential[] = useMemo(() => {
    return (credentialsData as any)?.items || (Array.isArray(credentialsData) ? credentialsData : []);
  }, [credentialsData]);

  const activeCredentials = useMemo(
    () => credentials.filter((c) => c.is_active !== false),
    [credentials]
  );

  const availableSops: Array<{ id: string; name: string; description?: string; category?: string }> = useMemo(() => {
    const list = (sopsData as any)?.items || (Array.isArray(sopsData) ? sopsData : []);
    return list;
  }, [sopsData]);

  // Modelle aus Models-Seite (echte Credentials + zentrale Default-Provider)
  const availableModels = useAvailableModels();

  // === FIX 23.06.2026 (BUG 488cff11bbe8): Pro Feld ein eigener PATCH-Call ===
  // Vorher: ein einzelner PATCH /api/subagents/{role}/config mit allen Feldern
  // Problem: dieser Endpoint existiert nicht im Backend -> Felder wurden stillschweigend ignoriert
  // Loesung: fuer jedes geaenderte Feld den entsprechenden spezifischen PATCH-Endpoint aufrufen
  const configMutation = useMutation({
    mutationFn: async ({ roleName, patch }: { roleName: string; patch: Partial<EditState> }) => {
      const calls: Promise<any>[] = []
      const callLog: string[] = []
      // Display-Name
      if (patch.display_name !== undefined) {
        calls.push(api.subagents.updateName(roleName, patch.display_name || ""))
        callLog.push("name")
      }
      // System-Prompt
      if (patch.system_prompt !== undefined) {
        calls.push(api.subagents.updatePrompt(roleName, patch.system_prompt || ""))
        callLog.push("prompt")
      }
      // SOP-ID
      if (patch.sop_id !== undefined) {
        calls.push(api.subagents.updateSop(roleName, patch.sop_id || null))
        callLog.push("sop")
      }
      // Model + Provider + API-Key-Id (ein gemeinsamer PATCH)
      if (patch.model !== undefined || patch.provider !== undefined || patch.api_key_id !== undefined) {
        calls.push(
          api.subagents.updateModel(
            roleName,
            patch.model || "",
            patch.provider,
            patch.api_key_id
          )
        )
        callLog.push("model")
      }
      // Sequentiell ausfuehren, damit Fehler frueh sichtbar werden
      const results: any[] = []
      for (const c of calls) {
        results.push(await c)
      }
      return { calls: callLog, results }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["subagent-configs"] })
      setEditingRole(null)
      setSaveMessage(`Gespeichert: ${data.calls.join(", ")}`)
      setTimeout(() => setSaveMessage(null), 3000)
    },
    onError: (e: any) => {
      setSaveError(`Speichern fehlgeschlagen: ${e?.message || String(e)}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (roleName: string) => api.subagents.delete(roleName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subagent-configs"] });
      setEditingRole(null);
    },
  });

  function handleDelete(c: AgentConfig) {
    if (deleteMutation.isPending) return;
    const shown = c.display_name && c.display_name.trim() ? c.display_name : c.name;
    const ok = window.confirm(
      `Sub-Agent "${shown}" (${c.name}) wirklich loeschen?\n\n` +
      `Hinweis: Historische Tasks und Token-Eintraege behalten den Rollennamen, ` +
      `aber Modell/Provider/Prompt gehen verloren. Diese Aktion ist nicht widerrufbar.`
    );
    if (ok) {
      deleteMutation.mutate(c.name);
    }
  }

  function startEdit(c: AgentConfig) {
    setEditingRole(c.name);
    setEditState(buildEdit(c));
  }

  function cancelEdit() {
    setEditingRole(null);
    setEditState(emptyEdit());
  }

  function saveEdit(c: AgentConfig) {
    const original = buildEdit(c);
    const patch: Partial<EditState> = {};
    if (editState.display_name !== original.display_name) patch.display_name = editState.display_name;
    if (editState.sop_id !== original.sop_id) patch.sop_id = editState.sop_id || null;
    if (editState.model !== original.model) patch.model = editState.model || null;
    if (editState.provider !== original.provider) patch.provider = editState.provider || null;
    if (editState.api_key_id !== original.api_key_id) patch.api_key_id = editState.api_key_id || null;
    if (editState.system_prompt !== original.system_prompt) patch.system_prompt = editState.system_prompt;

    // Wenn ein Credential automatisch verknuepft wurde, Model/Provider daraus uebernehmen
    if (editState.api_key_id) {
      const cred = credentials.find((x) => x.id === editState.api_key_id);
      if (cred) {
        patch.model = cred.model;
        patch.provider = cred.provider;
      }
    }

    if (Object.keys(patch).length === 0) {
      // Nichts geaendert -> nur schliessen
      setEditingRole(null);
      return;
    }
    configMutation.mutate({ roleName: c.name, patch });
  }

  function updateField<K extends keyof EditState>(field: K, value: EditState[K]) {
    setEditState((prev) => ({ ...prev, [field]: value }));
  }

  function handleCredentialChange(id: string) {
    const cred = credentials.find((x) => x.id === id);
    updateField("api_key_id", id);
    if (cred) {
      updateField("model", cred.model);
      updateField("provider", cred.provider);
    }
  }

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

  function sopNameFor(id?: string | null): string {
    if (!id) return "Keiner";
    const sop = availableSops.find((s) => s.id === id);
    return sop ? sop.name : id;
  }

  function renderAgentCard(c: AgentConfig, cLevelBadge?: boolean) {
    const isEditing = editingRole === c.name;
    const linkedCredential = credentials.find((cred) => cred.id === c.api_key_id);
    const shownName = c.display_name && c.display_name.trim() ? c.display_name : c.name;
    const hasCustomName = !!(c.display_name && c.display_name.trim());

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
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, flex: 1 }}>
            <span style={{ fontSize: 18, flexShrink: 0 }}>{c.emoji || "🤖"}</span>
            <strong style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {shownName}
            </strong>
            {hasCustomName && (
              <code
                style={{
                  fontSize: 10,
                  color: "var(--color-hermes-text-secondary)",
                  background: "var(--color-hermes-muted)",
                  padding: "1px 4px",
                  borderRadius: 3,
                }}
                title="Technischer Rollen-Identifier (intern, nicht ändern)"
              >
                {c.name}
              </code>
            )}
            {cLevelBadge && <span className="badge" style={{ fontSize: 9 }}>C-Level</span>}
          </div>
          {!isEditing && (
            <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
              <button
                className="btn btn-sm btn-danger"
                onClick={() => handleDelete(c)}
                disabled={deleteMutation.isPending}
                title="Sub-Agent loeschen (unwiderruflich)"
              >
                <Trash2 size={12} /> Loeschen
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={() => startEdit(c)}
                title="Rolle bearbeiten"
              >
                <Pencil size={12} /> Bearbeiten
              </button>
            </div>
          )}
        </div>

        {isEditing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <FieldRow label="Anzeigename" hint={`Leer = technischer Name "${c.name}"`}>
              <input
                className="input"
                value={editState.display_name}
                onChange={(e) => updateField("display_name", e.target.value)}
                placeholder={c.name}
                style={{ width: "100%" }}
              />
            </FieldRow>

            <FieldRow label="Modell" hint="Auswahl aus Models-Seite (echte Credentials + Standard-Provider)">
              <select
                className="select"
                value={editState.model}
                onChange={(e) => {
                  const raw = e.target.value;
                  // BUG-FIX 24.06.2026: Credential-Format "id:model" vs Default-Format "provider/model"
                  // auseinanderhalten, damit model nicht "<id>:minimax-m3" wird.
                  // 1) Suche zuerst nach Credential (Format: "<id>:<model>")
                  const cred = credentials.find((x) => `${x.id}:${x.model}` === raw);
                  if (cred) {
                    // Credential gewaehlt: model = reines model, api_key_id = credential.id
                    updateField("model", cred.model);
                    updateField("provider", cred.provider);
                    updateField("api_key_id", cred.id);
                  } else {
                    // Default-Modell (Format: "<provider>/<model>")
                    // Nur model-Feld setzen, KEIN api_key_id (sonst falsche Verknuepfung)
                    const m = raw.includes("/") ? raw.split("/").slice(1).join("/") : raw;
                    const provider = raw.includes("/") ? raw.split("/")[0] : "";
                    updateField("model", m);
                    if (provider) updateField("provider", provider);
                    updateField("api_key_id", "");
                  }
                }}
                style={{ width: "100%" }}
              >
                <option value="">— Modell waehlen —</option>
                {availableModels.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label="SOP (rein informativ)">
              <select
                className="select"
                value={editState.sop_id}
                onChange={(e) => updateField("sop_id", e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="">— Kein SOP —</option>
                {availableSops.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}{s.category ? ` (${s.category})` : ""}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label="Rollenbeschreibung (System-Prompt)">
              <textarea
                className="input"
                value={editState.system_prompt}
                onChange={(e) => updateField("system_prompt", e.target.value)}
                rows={8}
                style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: 12, resize: "vertical" }}
              />
            </FieldRow>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button type="button" className="btn" onClick={cancelEdit} disabled={configMutation.isPending}>
                <X size={12} /> Abbrechen
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => { setSaveError(null); setSaveMessage(null); saveEdit(c); }}
                disabled={configMutation.isPending}
              >
                <Save size={12} /> {configMutation.isPending ? "Speichern..." : "Speichern"}
              </button>
            </div>
            {saveError && (
              <div style={{ color: "var(--color-hermes-danger)", fontSize: 11, marginTop: 6, padding: 6, background: "rgba(220,38,38,0.1)", borderRadius: 4 }}>
                {saveError}
              </div>
            )}
            {saveMessage && !saveError && (
              <div style={{ color: "var(--color-hermes-accent)", fontSize: 11, marginTop: 6, padding: 6, background: "rgba(46,160,67,0.1)", borderRadius: 4 }}>
                {saveMessage}
              </div>
            )}
            {configMutation.isError && (
              <div style={{ color: "var(--color-hermes-danger)", fontSize: 11 }}>
                Fehler: {String(configMutation.error)}
              </div>
            )}
          </div>
        ) : (
          <div>
            <Row label="Modell" value={c.model || "(nicht gesetzt)"} />
            {c.default_model && c.model !== c.default_model && (
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2, marginLeft: 0 }}>
                Standard: <code>{c.default_model}</code>
              </div>
            )}
            <Row label="Provider" value={c.provider || "—"} />
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

            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 10, marginBottom: 4 }}>
              SOP (informativ)
            </div>
            {c.assigned_sop_id ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Workflow size={12} color="var(--color-hermes-accent-blue)" />
                <span style={{ fontSize: 12 }}>{sopNameFor(c.assigned_sop_id)}</span>
                <code style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                  {c.assigned_sop_id.slice(0, 8)}
                </code>
              </div>
            ) : (
              <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>Keiner</span>
            )}

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
        <PageId id={PAGE_IDS.SUB_AGENTS} />
        <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, margin: 0 }}>
          Jede Rolle hat einen API-Key/Provider, einen optionalen SOP-Verweis und eine editierbare Rollenbeschreibung.
          Alle Felder koennen gemeinsam ueber "Bearbeiten" geaendert und mit "Speichern" gespeichert werden.
        </p>
      </div>

      <h3 style={{ fontSize: 14, marginTop: 20, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        Sub-Agenten (Worker)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: 12 }}>
        {subagents.map((c: AgentConfig) => renderAgentCard(c))}
      </div>

      <h3 style={{ fontSize: 14, marginTop: 30, marginBottom: 10, color: "var(--color-hermes-text-secondary)" }}>
        C-Level Rollen (CIO, CEO-digital, etc.)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: 12 }}>
        {cLevel.map((c: AgentConfig) => renderAgentCard(c, true))}
      </div>
    </div>
  );
}

function FieldRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}>
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          {label}
        </label>
        {hint && (
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", opacity: 0.7 }}>
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 2 }}>{label}</div>
      <code style={{ fontSize: 12 }}>{value}</code>
    </div>
  );
}
