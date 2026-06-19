import { useState, useMemo, useEffect, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Activity, TrendingUp, Zap, Clock, AlertCircle, X } from "lucide-react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"

type Transition = {
  id: number
  task_id: string
  project_id?: string | null
  from_status: string
  to_status: string
  // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
  // Display-Namen vom Backend (z.B. "GO" statt "todo", "In Progress" statt
  // "in_progress"). Werden bevorzugt in der UI angezeigt.
  from_status_display?: string | null
  to_status_display?: string | null
  transition_at: string
  processing_at?: string | null
  completed_at?: string | null
  delay_s: number
  duration_ms?: number | null
  agent?: string | null
  reason?: string | null
  details?: Record<string, any>
  session_id?: string | null  // Optional — nur bei einigen Transitions vorhanden
}

const TRANSITION_COLORS: Record<string, string> = {
  "": "var(--color-hermes-text-secondary)",     // Initial
  "triage": "var(--color-hermes-accent-orange)",
  "todo": "var(--color-hermes-accent-blue)",
  "in_progress": "var(--color-hermes-accent)",
  "review": "#a371f7",
  "rueckfrage": "var(--color-hermes-danger)",
  "warten": "#58a6ff",
  "block": "var(--color-hermes-danger)",
  "done": "var(--color-hermes-accent)",
}

function StatusBadge({
  status,
  display,
  color,
}: {
  status: string
  display?: string | null
  color?: string
}) {
  // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
  // Wenn ein Display-Name vorhanden ist (z.B. "GO"), wird dieser bevorzugt
  // angezeigt. Andernfalls Fallback auf den DB-Key (z.B. "todo").
  const label = display || status || "∅"
  // Farb-Lookup muss auf den DB-Key basieren, damit die Farbpalette stabil bleibt
  const bg = color || TRANSITION_COLORS[status] || "var(--color-hermes-text-secondary)"
  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 6px",
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 600,
        background: `${bg}33`,
        color: bg,
        border: `1px solid ${bg}`,
        whiteSpace: "nowrap",
      }}
      title={display && display !== status ? `${display} (${status})` : status || ""}
    >
      {label}
    </span>
  )
}

export default function Performance() {
  const [projectFilter, setProjectFilter] = useState<string>("")
  const [taskFilter, setTaskFilter] = useState<string>("")
  const [fromFilter, setFromFilter] = useState<string>("")
  const [toFilter, setToFilter] = useState<string>("")
  const [limit, setLimit] = useState(200)
  // Selektion: wenn aktiv + taskFilter gesetzt, zeige nur Transitions dieses Tasks
  const [selectionActive, setSelectionActive] = useState(false)
  // Ausgewaehlte Transition fuer Detail-Sidebar (rechts)
  const [selectedTransition, setSelectedTransition] = useState<Transition | null>(null)

  // Projekte fuer Filter-Dropdown
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  })
  const projects: any[] = (projectsData as any)?.items || []

  // Tasks des aktuellen Projekts fuer Filter-Dropdown (zeigt Titel statt nur ID)
  const { data: projectTasksData } = useQuery({
    queryKey: ["tasks", projectFilter, "performance"],
    queryFn: () => projectFilter
      ? api.listTasks({ project_id: projectFilter, limit: 500 })
      : api.listTasks({ limit: 500 }),
  })
  const allTasks: any[] = (projectTasksData as any)?.items || []
  const taskTitleById: Record<string, string> = Object.fromEntries(
    allTasks.map((t: any) => [t.id, t.title || "(kein Titel)"])
  )

  // Transitions laden
  const { data: transitionsData, isLoading } = useQuery({
    queryKey: ["performance-transitions", projectFilter, taskFilter, fromFilter, toFilter, limit],
    queryFn: () => api.listTransitions({
      project_id: projectFilter || undefined,
      task_id: taskFilter || undefined,
      from_status: fromFilter || undefined,
      to_status: toFilter || undefined,
      limit,
    }),
  })
  const transitions: Transition[] = (transitionsData as any)?.items || []
  const total = (transitionsData as any)?.total || 0

  // Auto-Aktivierung: wenn ein Task im Dropdown gewaehlt wird, Selektion automatisch aktiv
  useEffect(() => {
    if (taskFilter) setSelectionActive(true)
  }, [taskFilter])

  // Globale Stats
  const { data: globalStats } = useQuery({
    queryKey: ["performance-stats-global"],
    queryFn: () => api.getGlobalPerformanceStats(),
  })

  // === Abgeleitete Stats ===
  const stats = useMemo(() => {
    if (transitions.length === 0) {
      return { avgDelay: 0, avgDuration: 0, byAgent: {} as Record<string, number>, byTransition: {} as Record<string, number> }
    }
    const totalDelay = transitions.reduce((s, t) => s + (t.delay_s || 0), 0)
    const totalDuration = transitions.reduce((s, t) => s + (t.duration_ms || 0), 0)
    const byAgent: Record<string, number> = {}
    const byTransition: Record<string, number> = {}
    for (const t of transitions) {
      const ag = t.agent || "unknown"
      byAgent[ag] = (byAgent[ag] || 0) + 1
      // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
      // Key mit Display-Namen bilden, damit die Top-Transitions-Liste
      // "GO → In Progress" statt "todo → in_progress" anzeigt.
      const fromLabel = t.from_status_display || t.from_status || "(initial)"
      const toLabel = t.to_status_display || t.to_status || "?"
      const key = `${fromLabel}→${toLabel}`
      byTransition[key] = (byTransition[key] || 0) + 1
    }
    return {
      avgDelay: totalDelay / transitions.length,
      avgDuration: totalDuration / transitions.length,
      byAgent,
      byTransition,
    }
  }, [transitions])

  // === Chart-Daten: Transitions pro Tag ===
  const chartData = useMemo(() => {
    const byDay: Record<string, number> = {}
    for (const t of transitions) {
      const day = t.transition_at?.slice(0, 10) || "?"
      byDay[day] = (byDay[day] || 0) + 1
    }
    return Object.entries(byDay)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-14) // letzte 14 Tage
      .map(([day, count]) => ({ day, count }))
  }, [transitions])

  const filtersActive = !!(projectFilter || taskFilter || fromFilter || toFilter)

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      {/* === Hauptbereich (links) === */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Activity size={20} color="var(--color-hermes-accent-blue)" />
          Performance
        </h1>
        <p>Task-Transitions, Verweildauer & Bottleneck-Analyse</p>
      </div>

      {/* === Global KPI Cards (kontextsensitiv) === */}
      {taskFilter ? (
        // Task-spezifische KPIs
        <TaskKpiCards transitions={transitions} taskTitle={taskTitleById[taskFilter]} />
      ) : (
        // Globale KPIs
        <div className="card-grid mb-3">
          <div className="stat-card">
            <span className="label"><Activity size={11} style={{ display: "inline", marginRight: 4 }} /> Transitions Total</span>
            <span className="value" style={{ color: "var(--color-hermes-accent-blue)" }}>
              {total}
            </span>
            <span className="sublabel">{transitions.length} geladen (Limit {limit})</span>
          </div>
          <div className="stat-card">
            <span className="label"><Clock size={11} style={{ display: "inline", marginRight: 4 }} /> Avg-Delay</span>
            <span className="value" style={{ color: "var(--color-hermes-accent-orange)" }}>
              {stats.avgDelay.toFixed(2)}s
            </span>
            <span className="sublabel">Soll: 5.0s (User-Transparenz)</span>
          </div>
          <div className="stat-card">
            <span className="label"><Zap size={11} style={{ display: "inline", marginRight: 4 }} /> Avg-Duration</span>
            <span className="value" style={{ color: "var(--color-hermes-accent)" }}>
              {stats.avgDuration.toFixed(0)}ms
            </span>
            <span className="sublabel">Verarbeitungsdauer pro Transition</span>
          </div>
          <div className="stat-card">
            <span className="label"><TrendingUp size={11} style={{ display: "inline", marginRight: 4 }} /> Top-Agent</span>
            <span className="value" style={{ color: "var(--color-hermes-accent)" }}>
              {Object.entries(stats.byAgent).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"}
            </span>
            <span className="sublabel">
              {Object.entries(stats.byAgent).sort((a, b) => b[1] - a[1])[0]?.[1] || 0} Transitions
            </span>
          </div>
        </div>
      )}


      {/* === Charts === */}
      <div className="card-grid mb-3" style={{ gridTemplateColumns: taskFilter ? "1fr" : "2fr 1fr" }}>
        {!taskFilter && (
        <div className="card">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>
            📈 Transitions pro Tag (letzte 14 Tage)
          </h3>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hermes-border)" />
                <XAxis dataKey="day" stroke="var(--color-hermes-text-secondary)" fontSize={10} />
                <YAxis stroke="var(--color-hermes-text-secondary)" fontSize={10} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", fontSize: 12 }} />
                <Line type="monotone" dataKey="count" stroke="var(--color-hermes-accent-blue)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 30 }}>
              Keine Daten fuer Zeitraum.
            </div>
          )}
        </div>
        )}
        <div className="card">
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 12px" }}>
            📊 Top-Transitions
          </h3>
          {Object.keys(stats.byTransition).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
              {Object.entries(stats.byTransition)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10)
                .map(([key, count]) => (
                  <div key={key} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 6px", background: "var(--color-hermes-muted)", borderRadius: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      {key}
                    </span>
                    <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 600, color: "var(--color-hermes-accent-blue)" }}>
                      {count}
                    </span>
                  </div>
                ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 30 }}>
              Keine Daten.
            </div>
          )}
        </div>
      </div>

      {/* === Filter-Bar (immer sichtbar) === */}
      <div className="triage-bar" style={{ marginBottom: 12 }}>
        <span style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>
          {transitions.length} / {total} Transitions
        </span>
        <div style={{ flex: 1 }} />
        <button
          className={`btn btn-sm ${selectionActive ? "btn-primary" : ""}`}
          onClick={() => setSelectionActive(!selectionActive)}
          disabled={!taskFilter}
          title={
            !taskFilter
              ? "Erst einen Task im Filter auswaehlen, dann Selektion aktivieren"
              : selectionActive
                ? "Selektion aktiv: zeigt nur Transitions dieses Tasks. Klick zum Deaktivieren."
                : "Klick zum Aktivieren: zeigt nur Transitions dieses Tasks."
          }
          style={{ fontSize: 11 }}
        >
          <span style={{ marginRight: 4 }}>🔍</span>
          Selektion
          {selectionActive && (
            <span
              className="badge"
              style={{
                marginLeft: 6,
                fontSize: 9,
                background: "rgba(255,255,255,0.25)",
                color: "white",
              }}
            >
              1 Task
            </span>
          )}
        </button>
        {filtersActive && (
          <button
            className="btn btn-sm"
            onClick={() => {
              setProjectFilter("")
              setTaskFilter("")
              setFromFilter("")
              setToFilter("")
              setSelectionActive(false)
            }}
          >
            ✕ Filter zurücksetzen
          </button>
        )}
      </div>

      {/* === Filter-Card (Excel/Sheets-Stil: Klick auf Feldname oeffnet Dropdown) === */}
      <div className="card mb-3" style={{ display: "grid", gridTemplateColumns: "1fr 2fr 1fr 1fr 120px", gap: 8, padding: 8 }}>
        <ExcelFilter
          label="Projekt"
          value={projectFilter}
          displayValue={projectFilter ? projects.find((p: any) => p.id === projectFilter)?.name || "(unbekannt)" : "Alle"}
          options={[
            { value: "", label: "Alle Projekte" },
            ...projects.map((p: any) => ({ value: p.id, label: p.name })),
          ]}
          onChange={(v) => { setProjectFilter(v); setTaskFilter("") }}
        />
        <TaskSearchField
          label="Task (Volltextsuche)"
          allTasks={allTasks}
          taskTitleById={taskTitleById}
          value={taskFilter}
          onChange={(v) => { setTaskFilter(v); if (v) setSelectionActive(true) }}
          highlight={!!taskFilter}
        />
        <ExcelFilter
          label="Von"
          value={fromFilter}
          displayValue={fromFilter || "Alle"}
          options={[
            { value: "", label: "Alle" },
            ...["triage", "todo", "in_progress", "review", "rueckfrage", "warten", "block", "done"].map((s) => ({ value: s, label: s })),
          ]}
          onChange={setFromFilter}
        />
        <ExcelFilter
          label="Nach"
          value={toFilter}
          displayValue={toFilter || "Alle"}
          options={[
            { value: "", label: "Alle" },
            ...["triage", "todo", "in_progress", "review", "rueckfrage", "warten", "block", "done"].map((s) => ({ value: s, label: s })),
          ]}
          onChange={setToFilter}
        />
        <ExcelFilter
          label="Limit"
          value={String(limit)}
          displayValue={String(limit)}
          options={["50", "100", "200", "500", "1000"].map((v) => ({ value: v, label: v }))}
          onChange={(v) => setLimit(Number(v))}
          align="right"
        />
      </div>


      {/* === Transition-Tabelle === */}
      <div className="card">
        <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <Activity size={14} /> Task-Transitions
          {total > 0 && <span className="badge badge-blue" style={{ fontSize: 10 }}>{total} total</span>}
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginLeft: 4, fontWeight: 400 }}>
            ↓ sortiert nach Zeit (neueste zuerst)
          </span>
          {selectionActive && taskFilter && (
            <span
              style={{
                marginLeft: 8,
                padding: "2px 8px",
                background: "rgba(46, 160, 67, 0.15)",
                border: "1px solid var(--color-hermes-accent)",
                borderRadius: 4,
                fontSize: 11,
                color: "var(--color-hermes-accent)",
                fontWeight: 600,
              }}
              title="Selektion-Filter aktiv: nur Transitions dieses Tasks werden geladen"
            >
              🎯 Selektion aktiv (nur {taskFilter.slice(0, 8)}…)
            </span>
          )}
          {taskFilter && taskTitleById[taskFilter] && (
            <span style={{ marginLeft: 8, padding: "2px 8px", background: "rgba(88,166,255,0.1)", border: "1px solid var(--color-hermes-accent-blue)", borderRadius: 4, fontSize: 11, color: "var(--color-hermes-accent-blue)" }}>
              🔍 Task: {taskTitleById[taskFilter]}
            </span>
          )}
        </h3>
        {isLoading ? (
          <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, padding: 20, textAlign: "center" }}>
            Lade Performance-Daten...
          </div>
        ) : transitions.length === 0 ? (
          <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, padding: 20, textAlign: "center" }}>
            <AlertCircle size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
            Keine Transitions gefunden. (Filter zuruecksetzen?)
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={{ width: 50 }}>ID</th>
                  <th style={{ width: 110 }}>Task-ID</th>
                  <th>Titel</th>
                  <th style={{ width: 110 }}>Von</th>
                  <th style={{ width: 110 }}>Nach</th>
                  <th style={{ width: 100 }}>Agent</th>
                  <th style={{ width: 160 }}>Session</th>
                  <th style={{ width: 140 }}>Reason</th>
                  <th style={{ width: 60 }}>Delay</th>
                  <th style={{ width: 70 }}>Duration</th>
                  <th style={{ width: 130 }}>Transition-At</th>
                  <th style={{ width: 130 }}>Completed-At</th>
                </tr>
              </thead>
              <tbody>
                {transitions.map((t) => {
                  const isActive = t.task_id === taskFilter
                  const isSelected = selectedTransition?.id === t.id
                  return (
                  <tr
                    key={t.id}
                    style={{
                      cursor: "pointer",
                      background: isSelected
                        ? "rgba(88,166,255,0.18)"
                        : isActive
                        ? "rgba(88,166,255,0.08)"
                        : undefined,
                    }}
                    onClick={() => setSelectedTransition(t)}
                    title="Klick: oeffnet Details in der Sidebar rechts"
                  >
                    <td className="mono" style={{ color: "var(--color-hermes-text-secondary)" }}>#{t.id}</td>
                    <td
                      className="mono"
                      onClick={() => {
                        if (taskFilter === t.task_id) {
                          setTaskFilter("")
                          setSelectionActive(false)
                        } else {
                          setTaskFilter(t.task_id)
                          setSelectionActive(true)
                        }
                      }}
                      style={{
                        cursor: "pointer",
                        fontSize: 10,
                        color: isActive ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text-secondary)",
                        fontWeight: isActive ? 700 : 400,
                        textDecoration: isActive ? "underline" : "none",
                      }}
                      title={isActive ? "Klick zum Aufheben der Auswahl" : `Klick: nur Transitions fuer Task ${t.task_id} anzeigen`}
                    >
                      {t.task_id} {isActive && "🎯"}
                    </td>
                    <td
                      onClick={() => {
                        if (taskFilter === t.task_id) {
                          setTaskFilter("")
                          setSelectionActive(false)
                        } else {
                          setTaskFilter(t.task_id)
                          setSelectionActive(true)
                        }
                      }}
                      style={{
                        cursor: "pointer",
                        fontSize: 11,
                        color: "var(--color-hermes-text)",
                        maxWidth: 300,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={taskTitleById[t.task_id] || t.task_id}
                    >
                      {taskTitleById[t.task_id] || <span style={{ color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>(unbekannt)</span>}
                    </td>
                    <td>
                      <StatusBadge status={t.from_status} display={t.from_status_display} />
                    </td>
                    <td>
                      <StatusBadge status={t.to_status} display={t.to_status_display} />
                    </td>
                    <td>
                      {t.agent ? (
                        <span className="badge badge-blue" style={{ fontSize: 10 }}>{t.agent}</span>
                      ) : (
                        <span style={{ color: "var(--color-hermes-text-secondary)" }}>—</span>
                      )}
                    </td>
                    <td
                      className="mono"
                      style={{ color: "var(--color-hermes-text-secondary)", fontSize: 10 }}
                      title={t.session_id || "Keine Session-ID (Backfill noetig fuer alte Transitions)"}
                    >
                      {t.session_id ? (
                        <span style={{ fontFamily: "monospace" }}>
                          {t.session_id.length > 18 ? t.session_id.slice(0, 15) + "..." : t.session_id}
                        </span>
                      ) : (
                        <span style={{ color: "var(--color-hermes-text-secondary)" }}>—</span>
                      )}
                    </td>
                    <td style={{ color: "var(--color-hermes-text-secondary)", fontSize: 10 }}>
                      {t.reason || "—"}
                    </td>
                    <td className="mono">
                      {t.delay_s != null ? `${t.delay_s.toFixed(1)}s` : "—"}
                    </td>
                    <td className="mono">
                      {t.duration_ms != null ? `${t.duration_ms}ms` : <span style={{ color: "var(--color-hermes-text-secondary)" }}>—</span>}
                    </td>
                    <td className="mono" style={{ fontSize: 10 }}>
                      {t.transition_at ? new Date(t.transition_at).toLocaleString("de-DE") : "—"}
                    </td>
                    <td className="mono" style={{ fontSize: 10 }}>
                      {t.completed_at ? new Date(t.completed_at).toLocaleString("de-DE") : <span style={{ color: "var(--color-hermes-text-secondary)" }}>pending</span>}
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Hinweis-Box unten */}
      {globalStats && (
        <div className="card mt-3" style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          <strong>ℹ️ Info:</strong> task_transitions dokumentiert <strong>jeden</strong> Status-Wechsel mit
          Verarbeitungs-Delay (default 5s fuer User-Transparenz). Vergleiche mit task_history (alle Events)
          und Token-Usage (Performance-Daten) fuer vollstaendiges Audit.
        </div>
      )}
      </div>

      {/* === Detail-Sidebar (rechts, analog zu Task-Detail-Panel) === */}
      <PerformanceDetailSidebar
        transition={selectedTransition}
        taskTitleById={taskTitleById}
        onClose={() => setSelectedTransition(null)}
        onFilterByTask={(taskId) => {
          setTaskFilter(taskId)
          setSelectionActive(true)
        }}
      />
    </div>
  )
}

// ─────────────── Performance Detail-Sidebar ───────────────
function PerformanceDetailSidebar({
  transition,
  taskTitleById,
  onClose,
  onFilterByTask,
}: {
  transition: Transition | null
  taskTitleById: Record<string, string>
  onClose: () => void
  onFilterByTask: (taskId: string) => void
}) {
  if (!transition) {
    return (
      <div
        className="detail-panel"
        style={{ minHeight: 400, display: "flex", flexDirection: "column" }}
      >
        <div className="detail-panel-header">
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-hermes-text-secondary)" }}>
            <Activity size={14} /> Performance-Detail
          </span>
        </div>
        <div className="detail-panel-body" style={{ display: "flex", alignItems: "center", justifyContent: "center", flex: 1, color: "var(--color-hermes-text-secondary)" }}>
          <div style={{ textAlign: "center", padding: 20 }}>
            <div style={{ fontSize: 36, opacity: 0.4, marginBottom: 8 }}>📊</div>
            <p style={{ margin: 0, fontSize: 12 }}>
              👉 Klick auf eine Zeile in der Tabelle, um Details zu sehen.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const t = transition
  const taskTitle = taskTitleById[t.task_id]

  return (
    <div className="detail-panel" style={{ display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div className="detail-panel-header">
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
          <span className="badge badge-blue" style={{ fontSize: 10 }}>#{t.id}</span>
          <Activity size={12} color="var(--color-hermes-accent-blue)" />
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Transition</span>
        </div>
        <button className="btn btn-sm" onClick={onClose} title="Schliessen" aria-label="Schliessen">
          <X size={12} />
        </button>
      </div>

      {/* Body */}
      <div className="detail-panel-body">
        {/* Titel: Transition-Name = "Von → Nach" */}
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px" }}>
          <StatusBadge status={t.from_status || "(initial)"} display={t.from_status_display} />
          <span style={{ margin: "0 6px", color: "var(--color-hermes-text-secondary)" }}>→</span>
          <StatusBadge status={t.to_status} display={t.to_status_display} />
        </h2>

        {/* Badges */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 12 }}>
          {t.agent && <span className="badge badge-blue" style={{ fontSize: 10 }}>👤 {t.agent}</span>}
          {t.reason && <span className="badge badge-gray" style={{ fontSize: 10 }}>⚡ {t.reason}</span>}
        </div>

        {/* Task-Bezug (klickbar zum Filtern) */}
        <div
          className="detail-panel-section"
          style={{ borderLeft: "3px solid var(--color-hermes-accent-blue)", cursor: "pointer" }}
          onClick={() => onFilterByTask(t.task_id)}
          title="Klick: alle Transitions dieses Tasks anzeigen"
        >
          <h4 style={{ margin: "0 0 4px", fontSize: 12 }}>📋 Task</h4>
          <div className="mono" style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
            {t.task_id}
          </div>
          <div style={{ fontSize: 12, color: "var(--color-hermes-text)" }}>
            {taskTitle || <em style={{ color: "var(--color-hermes-text-secondary)" }}>(unbekannt)</em>}
          </div>
        </div>

        {/* Performance-Metriken */}
        <div className="detail-panel-section">
          <h4 style={{ margin: "0 0 8px", fontSize: 12 }}>⏱ Performance</h4>
          <DetailRow label="Delay (Soll: 5s)" value={`${t.delay_s?.toFixed(2) ?? "—"}s`} />
          <DetailRow label="Duration" value={t.duration_ms != null ? `${t.duration_ms} ms` : "—"} />
          <DetailRow label="Project" value={t.project_id || "—"} mono />
        </div>

        {/* Zeitstempel */}
        <div className="detail-panel-section">
          <h4 style={{ margin: "0 0 8px", fontSize: 12 }}>🕐 Zeitstempel</h4>
          <DetailRow label="Transition-At" value={t.transition_at ? new Date(t.transition_at).toLocaleString("de-DE") : "—"} />
          <DetailRow label="Processing-At" value={t.processing_at ? new Date(t.processing_at).toLocaleString("de-DE") : "—"} />
          <DetailRow label="Completed-At" value={t.completed_at ? new Date(t.completed_at).toLocaleString("de-DE") : "—"} />
        </div>

        {/* Details / Reason */}
        {t.reason && (
          <div className="detail-panel-section">
            <h4 style={{ margin: "0 0 4px", fontSize: 12 }}>📌 Reason</h4>
            <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: 0, fontFamily: "var(--font-mono)" }}>
              {t.reason}
            </p>
          </div>
        )}

        {/* Details-JSON (falls vorhanden) */}
        {t.details && Object.keys(t.details).length > 0 && (
          <div className="detail-panel-section">
            <h4 style={{ margin: "0 0 4px", fontSize: 12 }}>🔍 Details</h4>
            <pre style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", margin: 0, background: "var(--color-hermes-muted)", padding: 6, borderRadius: 4, overflow: "auto" }}>
              {JSON.stringify(t.details, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────── Task-spezifische KPI-Cards ───────────────
function TaskKpiCards({ transitions, taskTitle }: { transitions: Transition[]; taskTitle?: string }) {
  // Aggregierte Werte
  const total = transitions.length
  const sorted = [...transitions].sort(
    (a, b) => new Date(a.transition_at || 0).getTime() - new Date(b.transition_at || 0).getTime()
  )
  const firstAt = sorted[0]?.transition_at
  const lastAt = sorted[sorted.length - 1]?.transition_at
  const totalDelay = transitions.reduce((s, t) => s + (t.delay_s || 0), 0)
  // Top-Agent dieses Tasks
  const agentCount: Record<string, number> = {}
  for (const t of transitions) {
    const ag = t.agent || "unknown"
    agentCount[ag] = (agentCount[ag] || 0) + 1
  }
  const topAgent = Object.entries(agentCount).sort((a, b) => b[1] - a[1])[0]
  // Erste und letzte Transition (Status-Pfad)
  const fromStatuses = Array.from(new Set(transitions.map((t) => t.from_status).filter(Boolean)))
  const toStatuses = Array.from(new Set(transitions.map((t) => t.to_status).filter(Boolean)))
  // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
  // Pfad mit Display-Namen rendern, damit der User "GO → In Progress"
  // sieht statt "todo → in_progress".
  const firstTrans = sorted[0]
  const lastTrans = sorted[sorted.length - 1]
  const firstFrom = firstTrans?.from_status_display || firstTrans?.from_status || fromStatuses[0] || "?"
  const lastTo = lastTrans?.to_status_display || lastTrans?.to_status || toStatuses[toStatuses.length - 1] || "?"
  const path = fromStatuses.length > 0 || toStatuses.length > 0
    ? `${firstFrom} → ${lastTo}`
    : "—"

  return (
    <div className="card-grid mb-3">
      <div className="stat-card" style={{ borderLeft: "3px solid var(--color-hermes-accent-blue)" }}>
        <span className="label" style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <Activity size={11} /> Transitions für diesen Task
        </span>
        <span className="value" style={{ color: "var(--color-hermes-accent-blue)" }}>
          {total}
        </span>
        <span className="sublabel" title={taskTitle || ""} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {taskTitle || "—"}
        </span>
      </div>
      <div className="stat-card">
        <span className="label"><Clock size={11} style={{ display: "inline", marginRight: 4 }} /> Erste → Letzte</span>
        <span className="value" style={{ color: "var(--color-hermes-text)", fontSize: 13 }}>
          {firstAt ? new Date(firstAt).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}
          <span style={{ color: "var(--color-hermes-text-secondary)", margin: "0 4px" }}>→</span>
          {lastAt ? new Date(lastAt).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}
        </span>
        <span className="sublabel">Pfad: {path}</span>
      </div>
      <div className="stat-card">
        <span className="label"><TrendingUp size={11} style={{ display: "inline", marginRight: 4 }} /> Top-Agent (Task)</span>
        <span className="value" style={{ color: "var(--color-hermes-accent)" }}>
          {topAgent ? topAgent[0] : "—"}
        </span>
        <span className="sublabel">{topAgent ? `${topAgent[1]} von ${total} Transitions` : "keine Daten"}</span>
      </div>
      <div className="stat-card">
        <span className="label">∑ Total-Delay</span>
        <span className="value" style={{ color: "var(--color-hermes-accent-orange)" }}>
          {totalDelay.toFixed(1)}s
        </span>
        <span className="sublabel">Summe aller Verzögerungen</span>
      </div>
    </div>
  )
}

// ─────────────── Detail-Row Helper (fuer Sidebar) ───────────────
function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        fontSize: 12,
        padding: "4px 0",
        borderBottom: "1px dashed var(--color-hermes-border)",
      }}
    >
      <span style={{ color: "var(--color-hermes-text-secondary)" }}>{label}</span>
      <span
        style={{
          color: "var(--color-hermes-text)",
          fontFamily: mono ? "var(--font-mono)" : undefined,
          fontSize: mono ? 11 : 12,
          textAlign: "right",
          maxWidth: 220,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={value}
      >
        {value}
      </span>
    </div>
  )
}

// ─────────────── Excel/Sheets-Style Filter-Dropdown ───────────────
// Klick auf den Label/Feldnamen oeffnet das Dropdown (wie in Excel/Sheets)
function ExcelFilter({
  label,
  value,
  displayValue,
  options,
  onChange,
  highlight,
  align,
}: {
  label: string
  value: string
  displayValue: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
  highlight?: boolean
  align?: "left" | "right"
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}
      >
        {/* Label = klickbarer Trigger (Excel/Sheets-Stil) */}
        <button
          className="excel-filter-trigger"
          onClick={() => setOpen(!open)}
          style={{
            fontSize: 10,
            color: highlight ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text-secondary)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            textAlign: align === "right" ? "right" : "left",
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 4,
            justifyContent: align === "right" ? "flex-end" : "flex-start",
          }}
          title={`Klick: ${label} filtern`}
        >
          <span>{label}</span>
          <span style={{ fontSize: 8, opacity: 0.7 }}>▼</span>
          {highlight && (
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-hermes-accent-blue)" }} />
          )}
        </button>
        {/* Display-Wert (read-only, zeigt aktuellen Filter) */}
        <div
          onClick={() => setOpen(!open)}
          style={{
            fontSize: 12,
            padding: "4px 6px",
            borderRadius: 3,
            background: highlight ? "rgba(88,166,255,0.1)" : "var(--color-hermes-muted)",
            border: `1px solid ${highlight ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-border)"}`,
            color: value ? "var(--color-hermes-text)" : "var(--color-hermes-text-secondary)",
            cursor: "pointer",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            minHeight: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: align === "right" ? "flex-end" : "flex-start",
          }}
        >
          {displayValue}
        </div>
      </div>

      {open && (
        <div
          className="excel-filter-menu"
          style={{
            position: "absolute",
            top: "calc(100% + 2px)",
            left: align === "right" ? "auto" : 0,
            right: align === "right" ? 0 : "auto",
            minWidth: "100%",
            maxWidth: 400,
            maxHeight: 300,
            overflowY: "auto",
            background: "var(--color-hermes-surface)",
            border: "1px solid var(--color-hermes-border)",
            borderRadius: 4,
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
            zIndex: 50,
          }}
        >
          {options.length === 0 ? (
            <div style={{ padding: "8px 10px", fontSize: 11, color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>
              Keine Optionen verfuegbar
            </div>
          ) : (
            options.map((o) => {
              const isCurrent = o.value === value
              return (
                <button
                  key={o.value || "_empty"}
                  className="excel-filter-item"
                  onClick={() => { onChange(o.value); setOpen(false) }}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "6px 10px",
                    fontSize: 12,
                    fontFamily: "inherit",
                    background: isCurrent ? "rgba(88,166,255,0.15)" : "transparent",
                    border: "none",
                    color: isCurrent ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text)",
                    textAlign: "left",
                    cursor: "pointer",
                    fontWeight: isCurrent ? 600 : 400,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={o.label}
                >
                  {isCurrent ? "✓ " : "  "}{o.label}
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

// === TaskSearchField — Volltextsuche fuer Tasks (User-Direktive 17.06.2026) ===
// Ersetzt das ExcelFilter-Dropdown durch ein freies Suchfeld.
// Suche in: task-id (auch Teilstring), title, description, status, assigned_role, tags
function TaskSearchField({
  label,
  allTasks,
  taskTitleById,
  value,
  onChange,
  highlight,
}: {
  label: string
  allTasks: any[]
  taskTitleById: Record<string, string>
  value: string
  onChange: (v: string) => void
  highlight?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Click-outside
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  // Aktuell ausgewaehlten Task-Titel anzeigen
  const selectedTitle = value ? taskTitleById[value] || "(unbekannt)" : ""

  // Volltext-Suche: durchsucht id, title, description, status, role, tags
  const q = query.trim().toLowerCase()
  const matches = q
    ? allTasks
        .filter((t) => {
          const fields = [
            t.id,
            t.title,
            t.description,
            t.status,
            t.assigned_role,
            (t.tags || []).join(" "),
          ].filter(Boolean).map((s) => String(s).toLowerCase())
          return fields.some((f) => f.includes(q))
        })
        .slice(0, 15)
    : allTasks.slice(0, 15)

  // Beim Oeffnen: Input fokussieren
  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  return (
    <div ref={ref} style={{ position: "relative", minWidth: 280 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <button
          className="excel-filter-trigger"
          onClick={() => setOpen(!open)}
          style={{
            fontSize: 10,
            color: highlight ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text-secondary)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            textAlign: "left",
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
          title={`Klick: ${label}`}
        >
          <span>{label}</span>
          <span style={{ fontSize: 8, opacity: 0.7 }}>▼</span>
          {highlight && (
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-hermes-accent-blue)" }} />
          )}
        </button>
        <div
          onClick={() => setOpen(!open)}
          style={{
            fontSize: 12,
            padding: "4px 8px",
            background: highlight ? "rgba(124, 58, 237, 0.1)" : "transparent",
            border: `1px solid ${highlight ? "var(--color-hermes-accent, #7c3aed)" : "transparent"}`,
            borderRadius: 4,
            cursor: "pointer",
            minHeight: 28,
            color: value ? "var(--color-hermes-text, #e5e5e5)" : "var(--color-hermes-text-secondary, #999)",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          {value ? (
            <>
              <code style={{ fontSize: 11, padding: "1px 4px", background: "rgba(255,255,255,0.05)", borderRadius: 3 }}>
                {value.slice(0, 12)}
              </code>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {selectedTitle}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onChange("") }}
                title="Filter loeschen"
                style={{
                  background: "transparent", border: "none", color: "#999",
                  cursor: "pointer", padding: 0, fontSize: 14,
                }}
              >×</button>
            </>
          ) : (
            <span style={{ fontStyle: "italic" }}>Tippen zum Suchen (ID, Titel, Beschreibung, Tags)</span>
          )}
        </div>
      </div>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 2px)",
            left: 0,
            right: 0,
            background: "var(--color-hermes-surface, #1a1a1a)",
            border: "1px solid var(--color-hermes-border, #444)",
            borderRadius: 6,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            zIndex: 1000,
            padding: 8,
            minWidth: 360,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tippen: z.B. 'a1b2c3' oder 'Login' oder 'GO' ..."
            style={{
              width: "100%", padding: "6px 10px", fontSize: 12,
              background: "var(--color-hermes-bg, #0a0a0a)",
              border: "1px solid var(--color-hermes-border, #333)",
              borderRadius: 4,
              color: "var(--color-hermes-text, #e5e5e5)",
              marginBottom: 8,
            }}
          />
          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #999)", marginBottom: 4, display: "flex", justifyContent: "space-between" }}>
            <span>{matches.length} Treffer {q && `(fuer "${q}")`}</span>
            {value && <span style={{ color: "var(--color-hermes-accent-blue)" }}>aktiv: {value.slice(0, 8)}</span>}
          </div>
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {matches.length === 0 ? (
              <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary, #999)", padding: 12, textAlign: "center", fontStyle: "italic" }}>
                Keine Treffer fuer "{q}". Anderen Suchbegriff versuchen.
              </div>
            ) : (
              matches.map((t) => (
                <div
                  key={t.id}
                  onClick={() => { onChange(t.id); setOpen(false); setQuery("") }}
                  style={{
                    padding: "6px 10px",
                    borderRadius: 4,
                    cursor: "pointer",
                    background: value === t.id ? "rgba(124, 58, 237, 0.2)" : "transparent",
                    fontSize: 12,
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                    marginBottom: 2,
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "rgba(124, 58, 237, 0.15)" }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = value === t.id ? "rgba(124, 58, 237, 0.2)" : "transparent" }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <code style={{ fontSize: 10, padding: "1px 4px", background: "rgba(255,255,255,0.05)", borderRadius: 3, fontFamily: "monospace" }}>
                      {t.id.slice(0, 12)}
                    </code>
                    <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #999)" }}>
                      {t.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--color-hermes-text, #e5e5e5)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {(t.title || "(kein Titel)").slice(0, 80)}
                  </div>
                </div>
              ))
            )}
          </div>
          <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary, #666)", marginTop: 8, textAlign: "right" }}>
            Tipp: Mindestens 3 Zeichen eingeben fuer praezise Treffer
          </div>
        </div>
      )}
    </div>
  )
}
