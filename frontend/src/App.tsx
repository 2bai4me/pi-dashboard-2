import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "./api"

type Tab = "projects" | "board" | "tasks" | "analytics" | "roles" | "pricing"

export default function App() {
  const [tab, setTab] = useState<Tab>("projects")
  const [activeProject, setActiveProject] = useState<string | null>(null)

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Pi Dashboard 2.0</h1>
        <div className="version">v2.0.0-beta · SQL</div>

        <a className={"nav-item" + (tab === "projects" ? " active" : "")} onClick={() => setTab("projects")}>
          📁 Projekte
        </a>
        <a className={"nav-item" + (tab === "board" ? " active" : "")} onClick={() => setTab("board")}>
          📋 Board
        </a>
        <a className={"nav-item" + (tab === "tasks" ? " active" : "")} onClick={() => setTab("tasks")}>
          ✅ Tasks
        </a>
        <a className={"nav-item" + (tab === "analytics" ? " active" : "")} onClick={() => setTab("analytics")}>
          📊 Analytics
        </a>
        <a className={"nav-item" + (tab === "pricing" ? " active" : "")} onClick={() => setTab("pricing")}>
          💰 Pricing
        </a>
        <a className={"nav-item" + (tab === "roles" ? " active" : "")} onClick={() => setTab("roles")}>
          👥 Rollen
        </a>

        <div style={{ marginTop: 24, padding: 12, background: "var(--bg-muted)", borderRadius: 6, fontSize: 11, color: "var(--text-dim)" }}>
          <div>Backend: <span className="mono">127.0.0.1:9220</span></div>
          <div>DB: SQLite (file-based)</div>
        </div>
      </aside>

      <main className="main">
        {tab === "projects" && <ProjectsTab activeProject={activeProject} setActiveProject={setActiveProject} />}
        {tab === "board" && <BoardTab activeProject={activeProject} setActiveProject={setActiveProject} />}
        {tab === "tasks" && <TasksTab activeProject={activeProject} />}
        {tab === "analytics" && <AnalyticsTab />}
        {tab === "pricing" && <PricingTab />}
        {tab === "roles" && <RolesTab />}
      </main>
    </div>
  )
}

// =================== PROJECTS ===================
function ProjectsTab({ activeProject, setActiveProject }: { activeProject: string | null; setActiveProject: (id: string) => void }) {
  const qc = useQueryClient()
  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  })
  const { data: analytics } = useQuery({ queryKey: ["analytics"], queryFn: () => api.getAnalytics() })

  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const create = useMutation({
    mutationFn: (data: any) => api.createProject(data),
    onSuccess: (p: any) => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      setShowNew(false)
      setName("")
      setDescription("")
      setActiveProject(p.id)
    },
  })

  const setMode = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: string }) => api.setProjectMode(id, mode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })

  if (isLoading) return <div>Lade...</div>
  const items = (projects as any)?.items || []

  return (
    <div>
      <div className="page-header">
        <h1>Projekte</h1>
        <p>Alle Projekte in der SQL-DB · {items.length} Einträge</p>
      </div>

      {analytics && (
        <div className="card-grid" style={{ marginBottom: 24 }}>
          <div className="card stat-card">
            <div className="label">Tasks gesamt</div>
            <div className="value">{(analytics as any).totals.tasks}</div>
          </div>
          <div className="card stat-card">
            <div className="label">History-Einträge</div>
            <div className="value">{(analytics as any).totals.history_entries}</div>
          </div>
          <div className="card stat-card">
            <div className="label">Tokens (in)</div>
            <div className="value mono">{(analytics as any).totals.tokens_in.toLocaleString("de-DE")}</div>
          </div>
          <div className="card stat-card">
            <div className="label">Gesamtkosten</div>
            <div className="value" style={{ color: "var(--danger)" }}>${(analytics as any).totals.cost_usd.toFixed(4)}</div>
          </div>
        </div>
      )}

      <div className="flex between mb-2">
        <h2 style={{ fontSize: 16, fontWeight: 600 }}>Projekt-Kacheln</h2>
        <button className="btn btn-primary" onClick={() => setShowNew(!showNew)}>
          {showNew ? "Abbrechen" : "+ Neues Projekt"}
        </button>
      </div>

      {showNew && (
        <div className="card">
          <input className="input mb-2" placeholder="Projekt-Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <textarea className="input" style={{ minHeight: 60 }} placeholder="Beschreibung" value={description} onChange={(e) => setDescription(e.target.value)} />
          <button className="btn btn-primary mt-2" onClick={() => create.mutate({ name, description })} disabled={!name || create.isPending}>
            Projekt anlegen
          </button>
        </div>
      )}

      <div className="card-grid">
        {items.map((p: any) => (
          <div key={p.id} className="card" style={{ borderLeft: `3px solid ${p.mode === "execution" ? "var(--accent)" : p.mode === "completed" ? "var(--accent-blue)" : "var(--text-dim)"}` }}>
            <div className="flex between mb-2">
              <strong style={{ fontSize: 14 }}>{p.name}</strong>
              <span className={"badge " + (p.mode === "preparation" ? "badge-gray" : p.mode === "execution" ? "badge-green" : p.mode === "paused" ? "badge-orange" : "badge-blue")}>
                {p.mode}
              </span>
            </div>
            <div className="text-sm text-dim mb-2">{p.description || "(keine)"}</div>
            <div className="row gap-2 text-xs text-dim mb-2">
              <span className="badge badge-gray">{p.category}</span>
              <span>{p.task_count} Tasks</span>
              <span>·</span>
              <span>${p.total_cost_usd.toFixed(4)}</span>
            </div>
            <div className="row gap-2">
              <select className="select" style={{ width: "auto" }} value={p.mode} onChange={(e) => setMode.mutate({ id: p.id, mode: e.target.value })}>
                <option value="preparation">Vorbereitung</option>
                <option value="execution">Umsetzung</option>
                <option value="paused">Pause</option>
                <option value="completed">Abgeschlossen</option>
              </select>
              <button className="btn btn-sm" onClick={() => { setActiveProject(p.id); setTab("board"); }}>
                Board →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// =================== BOARD ===================
function BoardTab({ activeProject, setActiveProject }: { activeProject: string | null; setActiveProject: (id: string) => void }) {
  const qc = useQueryClient()
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() })
  const projectId = activeProject || ((projects as any)?.items?.[0]?.id) || null
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId || undefined }),
    enabled: !!projectId,
  })

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.setTaskStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks", projectId] }),
  })

  const tasks = (tasksData as any)?.items || []
  const columns = ["triage", "todo", "in_progress", "review", "block", "done"]
  const columnLabels: Record<string, string> = {
    triage: "Triage", todo: "To Do", in_progress: "In Progress",
    review: "Review", block: "Block", done: "Done",
  }

  return (
    <div>
      <div className="page-header">
        <h1>Board</h1>
        <p>{projectId ? "Kanban-Board mit Live-SQL" : "Wähle ein Projekt in der Sidebar"}</p>
      </div>

      <div className="flex gap-4 mb-2">
        <span className="text-sm text-dim">Projekt:</span>
        <select className="select" style={{ width: 300 }} value={projectId || ""} onChange={(e) => setActiveProject(e.target.value)}>
          <option value="">— wählen —</option>
          {((projects as any)?.items || []).map((p: any) => (
            <option key={p.id} value={p.id}>{p.name} ({p.mode})</option>
          ))}
        </select>
        <span className="text-sm text-dim">· {tasks.length} Tasks</span>
      </div>

      <div className="board">
        {columns.map((col) => {
          const colTasks = tasks.filter((t: any) => t.status === col)
          return (
            <div key={col} className="column">
              <div className="column-header">
                <h3>{columnLabels[col]}</h3>
                <span className="column-count">{colTasks.length}</span>
              </div>
              {colTasks.map((t: any) => (
                <div key={t.id} className="task-card" onClick={() => setStatus.mutate({ id: t.id, status: col === "done" ? "in_progress" : "done" })}>
                  <div className="title">{t.title}</div>
                  <div className="meta">
                    <span className={"badge " + (t.priority >= 90 ? "badge-red" : t.priority >= 50 ? "badge-orange" : "badge-gray")}>
                      P{t.priority}
                    </span>
                    {t.assigned_role && <span className="badge badge-blue">{t.assigned_role}</span>}
                    {t.pricing_snapshot && <span className="badge badge-green">📸 snapshot</span>}
                    {t.emergency && <span className="badge badge-red">🚨</span>}
                  </div>
                </div>
              ))}
              {colTasks.length === 0 && <div className="text-xs text-dim" style={{ padding: 8, textAlign: "center" }}>— leer —</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// =================== TASKS ===================
function TasksTab({ activeProject }: { activeProject: string | null }) {
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", "all", activeProject],
    queryFn: () => api.listTasks({ project_id: activeProject || undefined }),
    enabled: true,
  })
  const tasks = (tasksData as any)?.items || []
  return (
    <div>
      <div className="page-header">
        <h1>Tasks</h1>
        <p>{tasks.length} Tasks</p>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th><th>Title</th><th>Status</th><th>Prio</th><th>Category</th><th>Role</th><th>Snapshot</th><th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t: any) => (
            <tr key={t.id}>
              <td className="mono text-xs">{t.id.slice(0, 8)}</td>
              <td>{t.title}</td>
              <td><span className="badge badge-gray">{t.status}</span></td>
              <td className="mono">{t.priority}</td>
              <td className="text-xs">{t.category}</td>
              <td className="text-xs">{t.assigned_role || "—"}</td>
              <td>{t.pricing_snapshot ? <span className="badge badge-green">✅</span> : <span className="text-dim">—</span>}</td>
              <td className="text-xs text-dim">{new Date(t.updated_at).toLocaleString("de-DE")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// =================== ANALYTICS ===================
function AnalyticsTab() {
  const { data, isLoading } = useQuery({ queryKey: ["analytics"], queryFn: () => api.getAnalytics() })
  if (isLoading) return <div>Lade...</div>
  const a: any = data
  return (
    <div>
      <div className="page-header">
        <h1>Analytics</h1>
        <p>Performance-Daten aus TokenUsage (SQL-Aggregation)</p>
      </div>
      <div className="card-grid">
        <div className="card stat-card">
          <div className="label">Tasks</div>
          <div className="value">{a.totals.tasks}</div>
        </div>
        <div className="card stat-card">
          <div className="label">History</div>
          <div className="value">{a.totals.history_entries}</div>
        </div>
        <div className="card stat-card">
          <div className="label">Tokens (in)</div>
          <div className="value mono">{a.totals.tokens_in.toLocaleString("de-DE")}</div>
        </div>
        <div className="card stat-card">
          <div className="label">Tokens (out)</div>
          <div className="value mono">{a.totals.tokens_out.toLocaleString("de-DE")}</div>
        </div>
        <div className="card stat-card">
          <div className="label">Gesamtkosten</div>
          <div className="value" style={{ color: "var(--danger)" }}>${a.totals.cost_usd.toFixed(4)}</div>
        </div>
      </div>
      <div className="card mt-2">
        <h3 className="mb-2" style={{ fontSize: 14, fontWeight: 600 }}>Status-Distribution</h3>
        <div className="row gap-4">
          {Object.entries(a.status_distribution).map(([s, c]: [string, any]) => (
            <div key={s}>
              <span className="badge badge-gray">{s}</span> <strong className="mono">{c}</strong>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h3 className="mb-2" style={{ fontSize: 14, fontWeight: 600 }}>Kosten pro Provider</h3>
        <div className="row gap-4">
          {Object.entries(a.cost_by_provider).map(([p, c]: [string, any]) => (
            <div key={p}>
              <span className="badge badge-blue">{p}</span> <strong className="mono">${c.toFixed(4)}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// =================== PRICING ===================
function PricingTab() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ["pricing"], queryFn: () => api.getPricing() })
  const refreshMut = useMutation({
    mutationFn: () => api.refreshPricing(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["pricing"] }); qc.invalidateQueries({ queryKey: ["analytics"] }) },
  })
  return (
    <div>
      <div className="page-header">
        <h1>Pricing</h1>
        <p>Provider-Preise aus SQL · Snapshot-Pattern bei Task-Start</p>
      </div>
      <div className="mb-2">
        <button className="btn btn-primary" onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}>
          🔄 Preise aktualisieren
        </button>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Provider</th><th>Modell</th><th>Input $/M</th><th>Output $/M</th>
            <th>Source</th><th>Last updated</th>
          </tr>
        </thead>
        <tbody>
          {data && Object.entries(data as any).flatMap(([prov, models]: [string, any]) =>
            Object.entries(models as any).map(([model, p]: [string, any]) => (
              <tr key={`${prov}/${model}`}>
                <td className="mono">{prov}</td>
                <td className="mono">{model}</td>
                <td className="mono">${p.input_per_1m}</td>
                <td className="mono">${p.output_per_1m}</td>
                <td className="text-xs text-dim">{p.source}</td>
                <td className="text-xs">{new Date(p.last_updated).toLocaleString("de-DE")}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// =================== ROLES ===================
function RolesTab() {
  const { data } = useQuery({ queryKey: ["roles"], queryFn: () => api.listRoles() })
  const roles = (data as any)?.items || []
  return (
    <div>
      <div className="page-header">
        <h1>Rollen</h1>
        <p>Sub-Agents + Organisationale Rollen</p>
      </div>
      <div className="card-grid">
        {roles.map((r: any) => (
          <div key={r.id} className="card">
            <div className="flex between mb-2">
              <strong>{r.name}</strong>
              <span className={"badge " + (r.role_type === "org" ? "badge-blue" : "badge-green")}>{r.role_type}</span>
            </div>
            <div className="text-sm text-dim mb-2">{r.description}</div>
            <div className="text-xs">
              <span className="badge badge-gray">{r.provider}/{r.model}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
