// Cost.tsx — Performance-Ansicht mit Task-Filter, Multi-Select und vollstaendigen Task-IDs
// Erweiterungen (User-Direktive 16.06.2026):
//   (1) Selektionsliste mit allen Tasks + Multi-Select
//   (2) Filter-Input fuer eine spezifische Task-ID
//   (3) Vollstaendige Task-IDs (Tooltip + Copy-Button)
//   (4) Drei Tabellen: transitions, history, token_usage fuer gefilterten Task
//   (5) Einheitliche TaskDetailPanel-Sidebar (Klick auf Task = gleiche Sidebar wie in Kanban)
import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Search, X, Copy, CheckCircle2, Filter, ListChecks } from "lucide-react"
import { TaskDetailPanel } from "../components/TaskDetailPanel"

export default function Cost() {
  const [days, setDays] = useState(30)
  const [taskIdFilter, setTaskIdFilter] = useState("")
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set())
  const [copiedId, setCopiedId] = useState<string | null>(null)
  // Sidebar-State: welcher Task ist selektiert? (User-Direktive 16.06.2026)
  const [sidebarTaskId, setSidebarTaskId] = useState<string | null>(null)

  // Globale Cost-Daten
  const { data, isLoading } = useQuery({
    queryKey: ["cost", days],
    queryFn: () => api.getCostSummary(days),
  })

  // Tasks-Liste (fuer Dropdown)
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", "all"],
    queryFn: () => api.listTasks({ limit: 500 }),
  })
  const allTasks: any[] = (tasksData as any)?.items || []

  // Task-spezifische Daten (wenn Filter aktiv)
  const { data: transitionsData } = useQuery({
    queryKey: ["performance-transitions", taskIdFilter],
    queryFn: () => api.listTransitions({ task_id: taskIdFilter, limit: 200 }),
    enabled: !!taskIdFilter,
  })
  const { data: taskDetailData } = useQuery({
    queryKey: ["task-detail", taskIdFilter],
    queryFn: () => api.getTask(taskIdFilter),
    enabled: !!taskIdFilter,
  })

  // Multi-Select Toggle
  function toggleSelect(taskId: string) {
    const newSet = new Set(selectedTasks)
    if (newSet.has(taskId)) newSet.delete(taskId)
    else newSet.add(taskId)
    setSelectedTasks(newSet)
  }

  function selectAll() {
    if (selectedTasks.size === allTasks.length) {
      setSelectedTasks(new Set())
    } else {
      setSelectedTasks(new Set(allTasks.map((t) => t.id)))
    }
  }

  function copyId(id: string) {
    navigator.clipboard.writeText(id)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  // Gefilterte Tasks (fuer Bulk-Operations)
  const filteredTasks = useMemo(() => {
    if (!taskIdFilter) return allTasks
    const q = taskIdFilter.toLowerCase()
    return allTasks.filter((t: any) =>
      t.id.toLowerCase().includes(q) ||
      (t.title || "").toLowerCase().includes(q)
    )
  }, [allTasks, taskIdFilter])

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Lade…</div>
  if (!data) return <div>Keine Daten</div>

  const byProvider = (data.by_provider || []).map((p: any) => ({ name: p.provider, cost: p.cost_usd }))
  const byDay = (data.by_day || []).map((d: any) => ({ day: d.day, cost: d.cost_usd, tokens_in: d.tokens_in, tokens_out: d.tokens_out }))
  const byModel = (data.by_model || []).map((m: any) => ({ name: m.model, tokens_in: m.tokens_in, tokens_out: m.tokens_out, cost: m.cost_usd, calls: m.calls }))
  const byRole = (data.by_role || []).map((r: any) => ({ name: r.role || "unknown", cost: r.cost_usd, calls: r.calls }))
  const total = data.total || { tokens_in: 0, tokens_out: 0, cost_usd: 0, calls: 0 }
  const transitions = (transitionsData as any)?.items || []
  const taskDetail = taskDetailData as any
  const taskHistory = (taskDetail as any)?.history || []

  return (
    <div>
      <div className="page-header">
        <h1>Cost & Usage</h1>
        <p>Token-Kosten & API-Aufrufe — letzte {days} Tage</p>
      </div>

      {/* Days-Filter (bestehend) */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {[7, 30, 90].map((d) => (
          <button key={d} className={`btn btn-sm ${d === days ? "btn-primary" : ""}`} onClick={() => setDays(d)}>
            {d}d
          </button>
        ))}
      </div>

      {/* === NEU: Task-Filter (User-Direktive 16.06.2026) === */}
      <div className="card" style={{ marginBottom: 16, padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Filter size={14} color="var(--color-hermes-accent-blue)" />
          <strong style={{ fontSize: 12 }}>Task-Filter:</strong>
          <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
            <Search size={12} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--color-hermes-text-secondary)" }} />
            <input
              className="input"
              placeholder="Task-ID eingeben (z.B. 4b1c10460604) oder Titel-Suche..."
              value={taskIdFilter}
              onChange={(e) => setTaskIdFilter(e.target.value)}
              style={{ paddingLeft: 26, fontSize: 12, width: "100%" }}
            />
          </div>
          {taskIdFilter && (
            <button className="btn btn-sm" onClick={() => setTaskIdFilter("")} title="Filter aufheben">
              <X size={12} /> Reset
            </button>
          )}
          <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            {filteredTasks.length} / {allTasks.length} Tasks
          </span>
        </div>
      </div>

      {/* === Stats (erweitert mit Token-Usage) === */}
      <div className="card-grid mb-3">
        <div className="stat-card">
          <span className="label">Gesamtkosten</span>
          <span className="value" style={{ color: "var(--color-hermes-danger)" }}>${total.cost_usd.toFixed(4)}</span>
        </div>
        <div className="stat-card">
          <span className="label">Tokens in</span>
          <span className="value" style={{ color: "var(--color-hermes-accent-blue)" }}>{(total.tokens_in || 0).toLocaleString("de-DE")}</span>
        </div>
        <div className="stat-card">
          <span className="label">Tokens out</span>
          <span className="value" style={{ color: "var(--color-hermes-accent)" }}>{(total.tokens_out || 0).toLocaleString("de-DE")}</span>
        </div>
        <div className="stat-card">
          <span className="label">API-Calls</span>
          <span className="value">{total.calls.toLocaleString("de-DE")}</span>
        </div>
        <div className="stat-card">
          <span className="label">Tasks total</span>
          <span className="value">{allTasks.length}</span>
        </div>
        <div className="stat-card">
          <span className="label">Ausgewaehlt</span>
          <span className="value" style={{ color: "var(--color-hermes-accent)" }}>{selectedTasks.size}</span>
        </div>
      </div>

      {byDay.length > 0 && (
        <div className="card mb-3">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>Kosten pro Tag</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={byDay}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hermes-border)" />
              <XAxis dataKey="day" stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <YAxis stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <Tooltip contentStyle={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)" }} />
              <Line type="monotone" dataKey="cost" stroke="var(--color-hermes-accent)" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {byProvider.length > 0 && (
        <div className="card mb-3">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>Kosten pro Provider</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byProvider}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hermes-border)" />
              <XAxis dataKey="name" stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <YAxis stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <Tooltip contentStyle={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)" }} />
              <Bar dataKey="cost" fill="var(--color-hermes-accent-blue)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {byRole.length > 0 && (
        <div className="card mb-3">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>Kosten pro Worker-Rolle</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byRole}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hermes-border)" />
              <XAxis dataKey="name" stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <YAxis stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <Tooltip contentStyle={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)" }} />
              <Bar dataKey="cost" fill="var(--color-hermes-accent-orange)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {byModel.length > 0 && (
        <div className="card mb-3">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>Token-Usage pro Modell (in/out)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byModel}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hermes-border)" />
              <XAxis dataKey="name" stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <YAxis stroke="var(--color-hermes-text-secondary)" fontSize={10} />
              <Tooltip contentStyle={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)" }} />
              <Bar dataKey="tokens_in" stackId="tokens" fill="var(--color-hermes-accent-blue)" name="Input Tokens" />
              <Bar dataKey="tokens_out" stackId="tokens" fill="var(--color-hermes-accent)" name="Output Tokens" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* === NEU: Selektionsliste mit allen Tasks + Multi-Select === */}
      <div className="card mb-3">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <ListChecks size={16} color="var(--color-hermes-accent-blue)" />
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: 0 }}>
            Tasks ({filteredTasks.length} {taskIdFilter ? `gefiltert` : "gesamt"})
          </h3>
          <div style={{ flex: 1 }} />
          <button className="btn btn-sm" onClick={selectAll}>
            {selectedTasks.size === allTasks.length ? "Alle abwaehlen" : "Alle auswaehlen"}
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 400, overflowY: "auto" }}>
          {filteredTasks.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
              Keine Tasks gefunden fuer "{taskIdFilter}"
            </div>
          ) : (
            filteredTasks.map((t: any) => (
              <div
                key={t.id}
                className="task-row"
                onClick={() => setSidebarTaskId(t.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 10px",
                  background: sidebarTaskId === t.id
                    ? "rgba(46, 160, 67, 0.15)"
                    : selectedTasks.has(t.id)
                    ? "rgba(46, 160, 67, 0.08)"
                    : "var(--color-hermes-surface)",
                  border: `1px solid ${sidebarTaskId === t.id ? "var(--color-hermes-accent)" : selectedTasks.has(t.id) ? "var(--color-hermes-accent)" : "var(--color-hermes-border)"}`,
                  borderRadius: 4,
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedTasks.has(t.id)}
                  onChange={() => toggleSelect(t.id)}
                  style={{ cursor: "pointer" }}
                />
                <span
                  className={`id-badge id-badge-board ${copiedId === t.id ? "id-badge-copied" : ""}`}
                  onClick={() => copyId(t.id)}
                  title={`Vollstaendige ID: ${t.id} (Klick zum Kopieren)`}
                  style={{ cursor: "pointer", minWidth: 100, fontFamily: "var(--font-mono)" }}
                >
                  {copiedId === t.id ? <><CheckCircle2 size={9} /> Kopiert!</> : t.id}
                </span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.title}
                </span>
                <span className={`badge ${t.status === "done" ? "badge-green" : t.status === "in_progress" ? "badge-blue" : "badge-orange"}`} style={{ fontSize: 10 }}>
                  {t.status}
                </span>
                <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Prio {t.priority}</span>
                <button className="btn btn-sm" onClick={() => copyId(t.id)} title="Task-ID kopieren" style={{ padding: "2px 6px" }}>
                  <Copy size={10} />
                </button>
              </div>
            ))
          )}
        </div>
        {selectedTasks.size > 0 && (
          <div style={{ marginTop: 12, padding: 8, background: "var(--color-hermes-muted)", borderRadius: 4, fontSize: 11 }}>
            <strong>{selectedTasks.size} Tasks ausgewaehlt.</strong> Bulk-Aktionen koennen hier folgen (z.B. "Status aendern", "Prio setzen", "Loeschen").
          </div>
        )}
      </div>

      {/* === NEU: Task-spezifische Daten (Transitions, History) === */}
      {taskIdFilter && taskDetail && (
        <>
          <div className="card mb-3">
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>
              Task-Details: {taskDetail.title}
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "4px 12px", fontSize: 12 }}>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Task-ID:</span>
              <code>{taskDetail.id}</code>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Status:</span>
              <span><span className="badge badge-blue">{taskDetail.status}</span></span>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Prio:</span>
              <span>{taskDetail.priority}</span>
              <span style={{ color: "var(--color-hermes-text-secondary)" }}>Category:</span>
              <span>{taskDetail.category}</span>
              {taskDetail.task_type && (
                <>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>Task-Type:</span>
                  <span>{taskDetail.task_type}</span>
                </>
              )}
            </div>
          </div>

          <div className="card mb-3">
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>
              Performance-Transitions ({transitions.length})
            </h3>
            {transitions.length === 0 ? (
              <div style={{ padding: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center" }}>
                Keine Transitions fuer diese Task-ID gefunden.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
                {transitions.map((tr: any) => (
                  <div key={tr.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 8px", background: "var(--color-hermes-surface)", borderRadius: 3 }}>
                    <code style={{ fontSize: 10 }}>{tr.transition_at?.slice(11, 19) || "—"}</code>
                    <span>{tr.from_status} → <strong>{tr.to_status}</strong></span>
                    <span style={{ color: "var(--color-hermes-text-secondary)" }}>· {tr.agent}</span>
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      {tr.duration_ms ? `${tr.duration_ms}ms` : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card mb-3">
            <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>
              Task-History ({taskHistory.length})
            </h3>
            {taskHistory.length === 0 ? (
              <div style={{ padding: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center" }}>
                Keine History-Eintraege vorhanden.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
                {taskHistory.slice(0, 20).map((h: any) => (
                  <div key={h.id} style={{ padding: "4px 8px", background: "var(--color-hermes-surface)", borderRadius: 3 }}>
                    <code style={{ fontSize: 10 }}>{h.ts?.slice(11, 19) || "—"}</code>
                    <strong style={{ marginLeft: 6 }}>{h.event}</strong>
                    <span style={{ color: "var(--color-hermes-text-secondary)", marginLeft: 6 }}>· {h.agent}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* === Einheitliche TaskDetailPanel-Sidebar (User-Direktive 16.06.2026) === */}
      {sidebarTaskId && (
        <TaskDetailPanel
          taskId={sidebarTaskId}
          projectName="(aus Performance-Ansicht)"
          onClose={() => setSidebarTaskId(null)}
        />
      )}
    </div>
  )
}
