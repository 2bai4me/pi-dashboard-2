import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { Key, Plus, Pencil, Trash2, Save, X, Eye, EyeOff, RefreshCw, DollarSign } from "lucide-react"

export type ProviderCredential = {
  id?: string
  provider: string
  model: string
  label: string
  api_key?: string
  base_url?: string
  is_active?: boolean
  input_cost_per_1m?: number | null
  output_cost_per_1m?: number | null
}

const EMPTY_CREDENTIAL: ProviderCredential = {
  provider: "",
  model: "",
  label: "",
  api_key: "",
  base_url: "",
  is_active: true,
  input_cost_per_1m: null,
  output_cost_per_1m: null,
}

const DEFAULT_PROVIDERS = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "kimi", label: "Kimi" },
  { value: "minimax-direct", label: "MiniMax" },
  { value: "ollama", label: "Ollama" },
  { value: "openai", label: "OpenAI / ChatGPT" },
  { value: "google", label: "Google / Gemini" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "github", label: "GitHub Models" },
]

const DEFAULT_MODEL_SUGGESTIONS: Record<string, string[]> = {
  deepseek: ["deepseek-4-pro", "deepseek-4-fast"],
  kimi: ["kimi-k2.7-code", "kimi-for-coding", "kimi-k2-thinking"],
  "minimax-direct": ["minimax-m3"],
  ollama: ["gemma4:12b"],
  openai: ["gpt-4o", "gpt-4", "gpt-3.5-turbo"],
  google: ["gemini-1.5-pro", "gemini-1.5-flash"],
  openrouter: ["openrouter/auto"],
  github: ["github/gpt-4o"],
}

function formatCost(value?: number | string | null): string {
  if (value === undefined || value === null || value === "") return "—"
  const num = typeof value === "string" ? parseFloat(value) : value
  if (Number.isNaN(num)) return "—"
  return `$${num.toFixed(4)}`
}

export default function ApiKeys() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<ProviderCredential | null>(null)
  const [showKeyIds, setShowKeyIds] = useState<Record<string, boolean>>({})

  const { data, isLoading, error } = useQuery({
    queryKey: ["provider-credentials"],
    queryFn: () => api.listProviderCredentials(),
  })

  const items: ProviderCredential[] = (data as any)?.items || []

  const saveMutation = useMutation({
    mutationFn: (credential: ProviderCredential) => {
      if (credential.id) {
        return api.updateProviderCredential(credential.id, credential)
      }
      return api.createProviderCredential(credential)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-credentials"] })
      setEditing(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteProviderCredential(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["provider-credentials"] }),
  })

  const refreshPricingMutation = useMutation({
    mutationFn: (id: string) => api.refreshProviderCredentialPricing(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["provider-credentials"] }),
  })

  function handleNew() {
    setEditing({ ...EMPTY_CREDENTIAL })
  }

  function handleEdit(credential: ProviderCredential) {
    setEditing({ ...credential })
  }

  function handleCancel() {
    setEditing(null)
  }

  function handleSave(credential: ProviderCredential) {
    saveMutation.mutate(credential)
  }

  function handleDelete(id?: string, label?: string) {
    if (!id) return
    if (window.confirm(`API-Key "${label || id}" wirklich löschen?`)) {
      deleteMutation.mutate(id)
    }
  }

  function handleRefreshPricing(id?: string) {
    if (!id) return
    refreshPricingMutation.mutate(id)
  }

  function toggleShowKey(id: string) {
    setShowKeyIds((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function updateEditing(field: keyof ProviderCredential, value: string | boolean | number | null) {
    setEditing((prev) => {
      if (!prev) return prev
      const next = { ...prev, [field]: value }
      if (field === "provider") {
        const suggestions = DEFAULT_MODEL_SUGGESTIONS[next.provider] || []
        if (suggestions.length > 0 && !suggestions.includes(next.model)) {
          next.model = suggestions[0]
        }
        if (!next.label) {
          const providerLabel = DEFAULT_PROVIDERS.find((p) => p.value === next.provider)?.label || next.provider
          next.label = `${providerLabel} ${next.model}`
        }
      }
      if (field === "model" && !next.label) {
        const providerLabel = DEFAULT_PROVIDERS.find((p) => p.value === next.provider)?.label || next.provider
        next.label = `${providerLabel} ${next.model}`
      }
      return next
    })
  }

  const isValid =
    editing &&
    editing.provider.trim() &&
    editing.model.trim() &&
    editing.label.trim()

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Key size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>API Keys</h1>
        </div>
        <p>Zentrale Verwaltung aller Provider-API-Keys, Modelle und Kosten pro 1 Mio Token</p>
      </div>

      {!editing && (
        <button className="btn btn-primary mb-3" onClick={handleNew} disabled={isLoading}>
          <Plus size={14} /> API-Key hinzufügen
        </button>
      )}

      {error && (
        <div className="toast toast-error" style={{ position: "static", marginBottom: 16 }}>
          Fehler beim Laden: {(error as Error).message}
        </div>
      )}

      {editing ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>
            {editing.id ? "API-Key bearbeiten" : "Neuer API-Key"}
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                Provider
              </label>
              <select
                className="select"
                value={editing.provider}
                onChange={(e) => updateEditing("provider", e.target.value)}
                required
              >
                <option value="">Provider wählen...</option>
                {DEFAULT_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                Modell
              </label>
              <input
                className="input"
                type="text"
                value={editing.model}
                onChange={(e) => updateEditing("model", e.target.value)}
                placeholder="z. B. deepseek-4-pro"
                list="model-suggestions"
                required
              />
              <datalist id="model-suggestions">
                {Object.values(DEFAULT_MODEL_SUGGESTIONS).flat().map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
              Bezeichnung
            </label>
            <input
              className="input"
              type="text"
              value={editing.label}
              onChange={(e) => updateEditing("label", e.target.value)}
              placeholder="z. B. DeepSeek 4 Pro"
              required
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                API-Key
              </label>
              <input
                className="input"
                type="password"
                value={editing.api_key || ""}
                onChange={(e) => updateEditing("api_key", e.target.value)}
                placeholder="sk-..."
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                Base-URL (optional)
              </label>
              <input
                className="input"
                type="text"
                value={editing.base_url || ""}
                onChange={(e) => updateEditing("base_url", e.target.value)}
                placeholder="https://api.example.com/v1"
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                Kosten / 1M Input-Tokens (USD, optional)
              </label>
              <input
                className="input"
                type="number"
                step="0.0001"
                min="0"
                value={editing.input_cost_per_1m ?? ""}
                onChange={(e) => {
                  const val = e.target.value
                  updateEditing("input_cost_per_1m", val === "" ? null : parseFloat(val))
                }}
                placeholder="0.0000"
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                Kosten / 1M Output-Tokens (USD, optional)
              </label>
              <input
                className="input"
                type="number"
                step="0.0001"
                min="0"
                value={editing.output_cost_per_1m ?? ""}
                onChange={(e) => {
                  const val = e.target.value
                  updateEditing("output_cost_per_1m", val === "" ? null : parseFloat(val))
                }}
                placeholder="0.0000"
              />
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <input
              id="is_active"
              type="checkbox"
              checked={editing.is_active ?? true}
              onChange={(e) => updateEditing("is_active", e.target.checked)}
            />
            <label htmlFor="is_active" style={{ fontSize: 13, margin: 0 }}>
              Aktiv
            </label>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn" onClick={handleCancel}>
              <X size={14} /> Abbrechen
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!isValid || saveMutation.isPending}
              onClick={() => handleSave(editing)}
            >
              <Save size={14} /> {saveMutation.isPending ? "Speichern..." : "Speichern"}
            </button>
          </div>
        </div>
      ) : isLoading ? (
        <div className="card">
          <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>Lade API-Keys...</p>
        </div>
      ) : items.length === 0 ? (
        <div className="card">
          <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
            Noch keine API-Keys hinterlegt.
          </p>
        </div>
      ) : (
        <div className="card-grid">
          {items.map((credential) => {
            const showKey = credential.id ? showKeyIds[credential.id] : false
            const hasPricing = credential.input_cost_per_1m != null || credential.output_cost_per_1m != null
            return (
              <div key={credential.id} className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 16 }}>{credential.label}</div>
                    <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                      {credential.provider} / {credential.model}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      className="btn btn-sm"
                      onClick={() => credential.id && handleRefreshPricing(credential.id)}
                      disabled={refreshPricingMutation.isPending}
                      title="Kosten per KI aktualisieren"
                    >
                      <RefreshCw size={14} className={refreshPricingMutation.isPending ? "spin" : ""} />
                    </button>
                    <button className="btn btn-sm" onClick={() => handleEdit(credential)} title="Bearbeiten">
                      <Pencil size={14} />
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleDelete(credential.id, credential.label)}
                      disabled={deleteMutation.isPending}
                      title="Löschen"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span>API-Key:</span>
                    <code style={{ fontSize: 11 }}>
                      {credential.api_key ? (showKey ? credential.api_key : "••••••••") : "—"}
                    </code>
                    {credential.api_key && (
                      <button
                        className="btn btn-sm"
                        onClick={() => credential.id && toggleShowKey(credential.id)}
                        title={showKey ? "Verbergen" : "Anzeigen"}
                      >
                        {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
                      </button>
                    )}
                  </div>
                  {credential.base_url && (
                    <div style={{ marginTop: 4 }}>Base-URL: {credential.base_url}</div>
                  )}
                </div>

                <div
                  style={{
                    marginTop: 8,
                    padding: 8,
                    background: "var(--color-hermes-muted)",
                    borderRadius: 4,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    flexWrap: "wrap",
                  }}
                >
                  <DollarSign size={14} color="var(--color-hermes-accent)" />
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: "var(--color-hermes-text-secondary)" }}>1M In:</span>{" "}
                    <strong>{formatCost(credential.input_cost_per_1m)}</strong>
                  </div>
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: "var(--color-hermes-text-secondary)" }}>1M Out:</span>{" "}
                    <strong>{formatCost(credential.output_cost_per_1m)}</strong>
                  </div>
                  {!hasPricing && (
                    <span className="badge" style={{ fontSize: 9 }}>Preis unbekannt</span>
                  )}
                </div>

                <div style={{ marginTop: 8 }}>
                  {credential.is_active ? (
                    <span className="badge badge-green">aktiv</span>
                  ) : (
                    <span className="badge">inaktiv</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
