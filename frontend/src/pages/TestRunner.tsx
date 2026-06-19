// TestRunner.tsx — Navigator-Service fuer Test-Aktionen
//
// User-Direktive 17.06.2026:
//   Zentraler Service, der vom Navigator ("Test Tool") aufgerufen wird.
//   Listet verfuegbare Aktionen und fuehrt sie aus.
//   Ergebnis wird in einem Result-Panel angezeigt.
//   History zeigt die letzten Ausfuehrungen.

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { api } from "../api"
import { SopInputToolConfigurator } from "../components/SopInputToolConfigurator"
import {
  Beaker,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  Loader2,
  Play,
  Sparkles,
  Wrench,
  XCircle,
  Zap,
} from "lucide-react"

const ICON_MAP: Record<string, any> = {
  "file-text": FileText,
  "zap": Zap,
  "wrench": Wrench,
  "sparkles": Sparkles,
  "beaker": Beaker,
}

const ICON_FOR_CATEGORY: Record<string, any> = {
  sop: FileText,
  agent: Zap,
  ops: Wrench,
  test: Beaker,
  general: Sparkles,
}

export default function TestRunner() {
  const [selectedAction, setSelectedAction] = useState<string | null>(null)
  const [params, setParams] = useState<Record<string, any>>({})
  const [result, setResult] = useState<any>(null)
  const queryClient = useQueryClient()

  // Aktionen laden
  const { data: actionsData, isLoading } = useQuery({
    queryKey: ["test-runner-actions"],
    queryFn: () => api.testRunner.listActions(),
  })

  // History laden
  const { data: historyData } = useQuery({
    queryKey: ["test-runner-history"],
    queryFn: () => api.testRunner.history(10),
    refetchInterval: 3000,
  })

  const actions: any[] = actionsData?.actions || []
  const history: any[] = historyData?.items || []

  // Beim Action-Wechsel: Defaults laden
  const handleSelectAction = (action: any) => {
    setSelectedAction(action.id)
    const defaults: Record<string, any> = {}
    for (const [key, schema] of Object.entries(action.params_schema || {})) {
      defaults[key] = (schema as any).default ?? ""
    }
    setParams(defaults)
    setResult(null)
  }

  // Mutation: Aktion ausfuehren
  const executeMut = useMutation({
    mutationFn: ({ id, params }: { id: string; params: any }) =>
      api.testRunner.executeAction(id, params),
    onSuccess: (data) => {
      setResult(data)
      queryClient.invalidateQueries({ queryKey: ["test-runner-history"] })
      // Auch AgentQuestions + Kanban refreshen
      queryClient.invalidateQueries({ queryKey: ["agent-questions"] })
      queryClient.invalidateQueries({ queryKey: ["agent-questions-pending"] })
    },
  })

  // SOP-Input-Tool-Configurator (eigener Modus)
  const [showConfigurator, setShowConfigurator] = useState(false)
  const [selectedSopId, setSelectedSopId] = useState<string | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)

  // SOPs laden
  const { data: sopsData } = useQuery({
    queryKey: ["sops"],
    queryFn: async () => {
      const res = await fetch("/api/sops")
      return res.json()
    },
  })
  const sops: any[] = (sopsData as any)?.items || []

  const handleExecute = () => {
    if (!selectedAction) return
    executeMut.mutate({ id: selectedAction, params })
  }

  const currentAction = actions.find((a) => a.id === selectedAction)

  return (
    <div>
      <div className="page-header">
        <h1>
          <Beaker size={20} style={{ marginRight: 8, verticalAlign: "text-bottom" }} />
          Test Tool
        </h1>
        <p>Service zum Ausfuehren von Test-Aktionen &middot; Navigator-Service</p>
      </div>

      <div
        style={{
          background: "rgba(124, 58, 237, 0.05)",
          border: "1px solid rgba(124, 58, 237, 0.3)",
          borderRadius: 8,
          padding: 14,
          marginBottom: 20,
          fontSize: 13,
          lineHeight: 1.5,
        }}
      >
        <strong>Hinweis:</strong> Dieses Tool ermoeglicht es, komplexe Aktionen per Knopfdruck
        auszufuehren, ohne die API direkt aufrufen zu muessen. Jede Aktion kann Parameter haben,
        die vor der Ausfuehrung gesetzt werden. Das Ergebnis wird inkl. weiterer Aktionen
        (z.B. offene Fragen) angezeigt.
        <div style={{ marginTop: 8 }}>
          <button
            onClick={() => setShowConfigurator(!showConfigurator)}
            style={{
              background: "transparent", color: "var(--color-hermes-accent, #7c3aed)",
              border: "1px solid var(--color-hermes-accent, #7c3aed)",
              borderRadius: 4, padding: "4px 10px", fontSize: 12, cursor: "pointer",
            }}
          >
            {showConfigurator ? "▼" : "▶"} SOP Input-Tool Konfigurator (Designer)
          </button>
        </div>
      </div>

      {/* SOP-Input-Tool-Configurator (einklappbar) */}
      {showConfigurator && (
        <div style={{
          background: "var(--color-hermes-bg-card, #1a1a1a)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderRadius: 8, padding: 20, marginBottom: 20,
        }}>
          <h3 style={{ marginTop: 0, fontSize: 14 }}>SOP-Designer: User-Input-Tool konfigurieren</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, marginBottom: 12 }}>
            <select
              value={selectedSopId || ""}
              onChange={(e) => { setSelectedSopId(e.target.value); setSelectedStepId(null); setShowConfigurator(true) }}
              style={{ padding: 6, background: "#0f0f0f", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4 }}
            >
              <option value="">SOP waehlen...</option>
              {sops.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            {selectedSopId && (
              <select
                value={selectedStepId || ""}
                onChange={(e) => setSelectedStepId(e.target.value)}
                style={{ padding: 6, background: "#0f0f0f", color: "#e5e5e5", border: "1px solid #333", borderRadius: 4 }}
              >
                <option value="">Step waehlen...</option>
                {sops.find((s) => s.id === selectedSopId)?.steps?.map((st: any) => (
                  <option key={st.id} value={st.id}>#{st.step_order} {st.name} (Agent: {st.agent})</option>
                ))}
              </select>
            )}
          </div>
          {selectedStepId && (() => {
            const sop = sops.find((s) => s.id === selectedSopId)
            const step = sop?.steps?.find((st: any) => st.id === selectedStepId)
            if (!step) return null
            return (
              <SopInputToolConfigurator
                sopId={selectedSopId}
                stepId={selectedStepId}
                step={step}
              />
            )
          })()}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: selectedAction ? "340px 1fr" : "1fr",
          gap: 16,
        }}
      >
        {/* Linke Spalte: Aktions-Liste + History */}
        <div>
          <h3 style={{ marginTop: 0, fontSize: 14, color: "var(--color-hermes-text-secondary, #999)", textTransform: "uppercase", letterSpacing: 0.5 }}>
            Verfuegbare Aktionen
          </h3>
          {isLoading ? (
            <div style={{ padding: 20, textAlign: "center" }}>
              <Loader2 size={20} className="spin" />
            </div>
          ) : actions.length === 0 ? (
            <div style={{ color: "#999", fontSize: 13, padding: 12 }}>Keine Aktionen definiert</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
              {actions.map((action) => {
                const Icon = ICON_MAP[action.icon] || ICON_FOR_CATEGORY[action.category] || Sparkles
                const isSelected = selectedAction === action.id
                return (
                  <button
                    key={action.id}
                    onClick={() => handleSelectAction(action)}
                    style={{
                      background: isSelected
                        ? "rgba(124, 58, 237, 0.15)"
                        : "var(--color-hermes-bg-card, #1a1a1a)",
                      border: `1px solid ${isSelected ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-border, #333)"}`,
                      borderLeft: `3px solid var(--color-hermes-accent, #7c3aed)`,
                      borderRadius: 6,
                      padding: "12px 14px",
                      cursor: "pointer",
                      textAlign: "left",
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      color: "var(--color-hermes-text, #e5e5e5)",
                    }}
                  >
                    <Icon size={18} style={{ color: "var(--color-hermes-accent, #7c3aed)", marginTop: 2, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{action.title}</div>
                      <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary, #999)", marginTop: 4, lineHeight: 1.4 }}>
                        {action.description.slice(0, 90)}
                        {action.description.length > 90 ? "..." : ""}
                      </div>
                    </div>
                    <ChevronRight size={14} style={{ color: "#999", marginTop: 4, flexShrink: 0 }} />
                  </button>
                )
              })}
            </div>
          )}

          {/* History */}
          {history.length > 0 && (
            <>
              <h3 style={{ fontSize: 14, color: "var(--color-hermes-text-secondary, #999)", textTransform: "uppercase", letterSpacing: 0.5 }}>
                Letzte Ausfuehrungen
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {history.map((h, i) => (
                  <div
                    key={i}
                    style={{
                      background: "rgba(0,0,0,0.2)",
                      border: "1px solid var(--color-hermes-border, #333)",
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 11,
                      color: "var(--color-hermes-text-secondary, #999)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Clock size={10} />
                      <span style={{ flex: 1 }}>{new Date(h.ts).toLocaleTimeString("de-DE")}</span>
                      {h.result?.ok ? (
                        <CheckCircle2 size={10} color="#10b981" />
                      ) : (
                        <XCircle size={10} color="#dc2626" />
                      )}
                    </div>
                    <div style={{ marginTop: 2, color: "var(--color-hermes-text, #e5e5e5)" }}>
                      {h.action_id}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Rechte Spalte: Action-Detail + Result */}
        {currentAction && (
          <ActionDetail
            action={currentAction}
            params={params}
            setParams={setParams}
            onExecute={handleExecute}
            isExecuting={executeMut.isPending}
            result={result}
          />
        )}
      </div>
    </div>
  )
}

// =====================================================
//  Action Detail (rechte Spalte)
// =====================================================
function ActionDetail({ action, params, setParams, onExecute, isExecuting, result }: {
  action: any
  params: Record<string, any>
  setParams: (p: Record<string, any>) => void
  onExecute: () => void
  isExecuting: boolean
  result: any | null
}) {
  const Icon = ICON_MAP[action.icon] || ICON_FOR_CATEGORY[action.category] || Sparkles
  const paramEntries = Object.entries(action.params_schema || {}) as [string, any][]

  return (
    <div>
      {/* Header */}
      <div
        style={{
          background: "var(--color-hermes-bg-card, #1a1a1a)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderLeft: "3px solid var(--color-hermes-accent, #7c3aed)",
          borderRadius: 8,
          padding: 20,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div
            style={{
              background: "rgba(124, 58, 237, 0.15)",
              color: "var(--color-hermes-accent, #7c3aed)",
              padding: 10,
              borderRadius: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon size={22} />
          </div>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: "0 0 6px 0", fontSize: 18 }}>{action.title}</h2>
            <div style={{ fontSize: 13, color: "var(--color-hermes-text-secondary, #999)", lineHeight: 1.5 }}>
              {action.description}
            </div>
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--color-hermes-text-secondary, #999)" }}>
              <strong>ID:</strong> <code>{action.id}</code> · <strong>Category:</strong> {action.category}
            </div>
          </div>
        </div>
      </div>

      {/* Parameter */}
      {paramEntries.length > 0 && (
        <div
          style={{
            background: "var(--color-hermes-bg-card, #1a1a1a)",
            border: "1px solid var(--color-hermes-border, #333)",
            borderRadius: 8,
            padding: 20,
            marginBottom: 16,
          }}
        >
          <h3 style={{ marginTop: 0, fontSize: 14 }}>Parameter</h3>
          {paramEntries.map(([key, schema]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <label
                style={{
                  display: "block",
                  fontSize: 12,
                  fontWeight: 600,
                  marginBottom: 4,
                  color: "var(--color-hermes-text, #e5e5e5)",
                }}
              >
                {key}
                {schema.required && <span style={{ color: "#dc2626" }}> *</span>}
                <span style={{ color: "#999", fontWeight: 400, marginLeft: 6 }}>
                  ({schema.type})
                </span>
              </label>
              {schema.type === "text" ? (
                <textarea
                  value={params[key] || ""}
                  onChange={(e) => setParams({ ...params, [key]: e.target.value })}
                  rows={3}
                  style={{
                    width: "100%",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid var(--color-hermes-border, #333)",
                    borderRadius: 4,
                    padding: 8,
                    color: "var(--color-hermes-text, #e5e5e5)",
                    fontSize: 13,
                    fontFamily: "inherit",
                    boxSizing: "border-box",
                  }}
                />
              ) : (
                <input
                  type="text"
                  value={params[key] || ""}
                  onChange={(e) => setParams({ ...params, [key]: e.target.value })}
                  style={{
                    width: "100%",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid var(--color-hermes-border, #333)",
                    borderRadius: 4,
                    padding: 8,
                    color: "var(--color-hermes-text, #e5e5e5)",
                    fontSize: 13,
                    boxSizing: "border-box",
                  }}
                />
              )}
              {schema.description && (
                <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>
                  {schema.description}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Execute-Button */}
      <button
        onClick={onExecute}
        disabled={isExecuting}
        style={{
          background: "var(--color-hermes-accent, #7c3aed)",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          padding: "12px 20px",
          fontSize: 14,
          fontWeight: 600,
          cursor: isExecuting ? "wait" : "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          opacity: isExecuting ? 0.7 : 1,
          marginBottom: 20,
        }}
      >
        {isExecuting ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
        Aktion ausfuehren
      </button>

      {/* Result */}
      {result && <ActionResult result={result} />}
    </div>
  )
}

// =====================================================
//  Result Panel
// =====================================================
function ActionResult({ result }: { result: any }) {
  const ok = result.ok !== false
  return (
    <div
      style={{
        background: ok ? "rgba(16, 185, 129, 0.05)" : "rgba(220, 38, 38, 0.05)",
        border: `1px solid ${ok ? "rgba(16, 185, 129, 0.4)" : "rgba(220, 38, 38, 0.4)"}`,
        borderLeft: `3px solid ${ok ? "#10b981" : "#dc2626"}`,
        borderRadius: 8,
        padding: 20,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        {ok ? <CheckCircle2 size={20} color="#10b981" /> : <XCircle size={20} color="#dc2626" />}
        <strong style={{ fontSize: 16, color: ok ? "#10b981" : "#dc2626" }}>
          {ok ? "Erfolgreich" : "Fehler"}
        </strong>
        {result.action && (
          <code style={{ fontSize: 12, color: "#999", marginLeft: 8 }}>
            {result.action}
          </code>
        )}
      </div>

      {/* Task-Highlight (wenn start-iscp) */}
      {result.task && (
        <div
          style={{
            background: "rgba(124, 58, 237, 0.1)",
            border: "1px solid rgba(124, 58, 237, 0.3)",
            borderRadius: 6,
            padding: 12,
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <FileText size={18} color="var(--color-hermes-accent, #7c3aed)" />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "#999" }}>Task erstellt in {result.project?.name}</div>
            <div style={{ fontWeight: 600 }}>{result.task.title}</div>
            <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
              ID: <code>{result.task.id}</code> · Status: {result.task.status} · Agent: {result.task.assigned_role}
            </div>
          </div>
          <Link
            to={`/kanban?task=${result.task.id}`}
            style={{
              background: "transparent",
              border: "1px solid var(--color-hermes-accent, #7c3aed)",
              color: "var(--color-hermes-accent, #7c3aed)",
              padding: "4px 8px",
              borderRadius: 4,
              fontSize: 11,
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <ExternalLink size={11} /> Im Board
          </Link>
        </div>
      )}

      {/* Instance-Highlight */}
      {result.instance && (
        <div
          style={{
            background: "rgba(0,0,0,0.2)",
            border: "1px solid var(--color-hermes-border, #333)",
            borderRadius: 6,
            padding: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ fontSize: 12, color: "#999" }}>SOP-Instance gestartet</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            <strong>{result.sop?.name}</strong>
            <code style={{ fontSize: 11, color: "#999" }}>({result.sop?.id})</code>
          </div>
          <div style={{ fontSize: 12, marginTop: 4 }}>
            Step: <strong>{result.instance.current_step_name}</strong> (ID: <code>{result.instance.current_step_id}</code>)
          </div>
          <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
            Instance: <code>{result.instance.id}</code> · Status: {result.instance.status}
          </div>
        </div>
      )}

      {/* Next-Action-Hint */}
      {result.next_action && (
        <div
          style={{
            background: "rgba(245, 158, 11, 0.1)",
            border: "1px solid rgba(245, 158, 11, 0.4)",
            borderRadius: 6,
            padding: 10,
            fontSize: 13,
            color: "#f59e0b",
            marginBottom: 12,
          }}
        >
          <strong>Nächster Schritt:</strong> {result.next_action}
        </div>
      )}

      {/* Link zu Tools-Tab */}
      <div style={{ marginTop: 8 }}>
        <Link
          to="/tools/agent-questions"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            color: "var(--color-hermes-accent, #7c3aed)",
            textDecoration: "none",
            fontSize: 13,
          }}
        >
          <Sparkles size={14} /> Offene Fragen im User-Input-Tool anzeigen
          <ExternalLink size={11} />
        </Link>
      </div>

      {/* Raw JSON (zum Debuggen, einklappbar) */}
      <details style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", color: "#999", fontSize: 12 }}>Raw JSON Response</summary>
        <pre
          style={{
            background: "rgba(0,0,0,0.4)",
            padding: 10,
            borderRadius: 4,
            fontSize: 11,
            overflow: "auto",
            marginTop: 6,
            color: "#a5b4fc",
          }}
        >
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  )
}
