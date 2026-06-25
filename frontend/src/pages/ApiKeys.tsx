import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { DEFAULT_PROVIDER_TILES, isLocalProvider } from "../providerDefaults"
import { Plus, Pencil, Trash2, Save, X, Eye, EyeOff, RefreshCw, DollarSign, Key, Server } from "lucide-react"

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

// Diese Provider werden immer als Kachel angezeigt – auch wenn keine Credentials hinterlegt sind.
// Quelle: frontend/src/providerDefaults.ts (zentral, wird auch im SOP-ModelSelect genutzt)

const PROVIDER_OPTIONS = [
  { value: "kimi", label: "Kimi" },
  { value: "minimax-direct", label: "MiniMax" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "ollama", label: "Ollama" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai", label: "OpenAI / ChatGPT" },
  { value: "google", label: "Google / Gemini" },
  { value: "github", label: "GitHub Models" },
]

const DEFAULT_MODEL_SUGGESTIONS: Record<string, string[]> = {
  kimi: ["kimi-k2.7-code", "kimi-for-coding", "kimi-k2-thinking"],
  "minimax-direct": ["minimax-m3"],
  openrouter: ["openrouter/auto", "anthropic/claude-sonnet-4", "openai/gpt-4o"],
  ollama: ["gemma4:12b", "qwen3:8b", "llama3.1:70b"],
  deepseek: ["deepseek-4-pro", "deepseek-4-fast"],
  openai: ["gpt-4o", "gpt-4", "gpt-3.5-turbo"],
  google: ["gemini-1.5-pro", "gemini-1.5-flash"],
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

  function handleNew(provider?: string, model?: string) {
    const base: ProviderCredential = { ...EMPTY_CREDENTIAL }
    if (provider) base.provider = provider
    if (model) base.model = model
    if (provider && model) {
      const providerLabel = PROVIDER_OPTIONS.find((p) => p.value === provider)?.label || provider
      base.label = `${providerLabel} ${model}`
    }
    setEditing(base)
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
          const providerLabel = PROVIDER_OPTIONS.find((p) => p.value === next.provider)?.label || next.provider
          next.label = `${providerLabel} ${next.model}`
        }
      }
      if (field === "model" && !next.label) {
        const providerLabel = PROVIDER_OPTIONS.find((p) => p.value === next.provider)?.label || next.provider
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

  // === Kachel-Liste: alle hinterlegten Credentials + 4 Default-Provider, falls noch nicht vorhanden ===
  const tileMap = new Map<string, ProviderCredential>()
  for (const c of items) tileMap.set(`${c.provider}::${c.model}`, c)
  const tiles: { credential: ProviderCredential; isDefault: boolean }[] = []
  for (const def of DEFAULT_PROVIDER_TILES) {
    const existing = tileMap.get(`${def.provider}::${def.model}`)
    tiles.push({ credential: existing || (def as ProviderCredential), isDefault: !existing })
  }
  // zusätzliche Credentials (z. B. DeepSeek) ebenfalls anzeigen
  for (const c of items) {
    const key = `${c.provider}::${c.model}`
    const isDefault = DEFAULT_PROVIDER_TILES.some((d) => `${d.provider}::${d.model}` === key)
    if (!isDefault) tiles.push({ credential: c, isDefault: false })
  }

  return (
    <div>
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
                {PROVIDER_OPTIONS.map((p) => (
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
                placeholder="z. B. kimi-k2.7-code"
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
              placeholder="z. B. Kimi K2.7 Code"
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
                Kosten / 1M Input-Tokens (USD)
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
                Kosten / 1M Output-Tokens (USD)
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
          <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>Lade Provider...</p>
        </div>
      ) : (
        // Schmaleres Grid: mind. 180px pro Kachel, füllt die Reihe auf
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
          {tiles.map(({ credential, isDefault }) => {
            const showKey = credential.id ? showKeyIds[credential.id] : false
            const hasKey = !!(credential.api_key && credential.api_key.length > 0)
            const hasPricing = credential.input_cost_per_1m != null || credential.output_cost_per_1m != null
            const isLocal = isLocalProvider(credential.provider)
            return (
              <div key={`${credential.provider}::${credential.model}`} className="card" style={{ padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 4, marginBottom: 6 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {credential.label}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {credential.provider} / {credential.model}
                    </div>
                  </div>
                  {isLocal && (
                    <span
                      className="badge"
                      style={{ fontSize: 9, display: "inline-flex", alignItems: "center", gap: 3, flexShrink: 0 }}
                      title="Lokales Modell – kein API-Key erforderlich"
                    >
                      <Server size={9} /> lokal
                    </span>
                  )}
                  {!isDefault && credential.id && (
                    <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
                      <button
                        className="btn btn-sm"
                        style={{ padding: 2 }}
                        onClick={() => handleRefreshPricing(credential.id)}
                        disabled={refreshPricingMutation.isPending}
                        title="Kosten per KI aktualisieren"
                      >
                        <RefreshCw size={11} className={refreshPricingMutation.isPending ? "spin" : ""} />
                      </button>
                      <button className="btn btn-sm" style={{ padding: 2 }} onClick={() => handleEdit(credential)} title="Bearbeiten">
                        <Pencil size={11} />
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        style={{ padding: 2 }}
                        onClick={() => handleDelete(credential.id, credential.label)}
                        disabled={deleteMutation.isPending}
                        title="Löschen"
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  )}
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    padding: "4px 6px",
                    background: "var(--color-hermes-muted)",
                    borderRadius: 3,
                    fontSize: 10,
                    color: "var(--color-hermes-text-secondary)",
                  }}
                >
                  <Key size={10} />
                  <span>
                    {isLocal
                      ? "kein Key erforderlich (lokal)"
                      : hasKey
                        ? (showKey ? credential.api_key : "••••••••")
                        : "nicht hinterlegt"}
                  </span>
                  {hasKey && credential.id && !isLocal && (
                    <button
                      className="btn btn-sm"
                      style={{ padding: 0, marginLeft: "auto", border: "none", background: "transparent" }}
                      onClick={() => toggleShowKey(credential.id!)}
                      title={showKey ? "Verbergen" : "Anzeigen"}
                    >
                      {showKey ? <EyeOff size={10} /> : <Eye size={10} />}
                    </button>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 10 }}>
                  <DollarSign size={10} color="var(--color-hermes-accent)" />
                  <span>
                    In: <strong>{formatCost(credential.input_cost_per_1m)}</strong>
                  </span>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>·</span>
                  <span>
                    Out: <strong>{formatCost(credential.output_cost_per_1m)}</strong>
                  </span>
                  {!hasPricing && !isLocal && (
                    <span className="badge" style={{ fontSize: 8, marginLeft: "auto" }}>?</span>
                  )}
                </div>

                <div style={{ marginTop: 6, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  {isLocal ? (
                    <span className="badge badge-green" style={{ fontSize: 9 }}>einsatzbereit</span>
                  ) : isDefault ? (
                    !hasKey ? (
                      <button
                        className="btn btn-sm btn-primary"
                        style={{ padding: "2px 6px", fontSize: 10 }}
                        onClick={() => handleNew(credential.provider, credential.model)}
                      >
                        <Plus size={10} /> Hinzufügen
                      </button>
                    ) : credential.is_active ? (
                      <span className="badge badge-green" style={{ fontSize: 9 }}>aktiv</span>
                    ) : (
                      <span className="badge" style={{ fontSize: 9 }}>inaktiv</span>
                    )
                  ) : credential.is_active ? (
                    <span className="badge badge-green" style={{ fontSize: 9 }}>aktiv</span>
                  ) : (
                    <span className="badge" style={{ fontSize: 9 }}>inaktiv</span>
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