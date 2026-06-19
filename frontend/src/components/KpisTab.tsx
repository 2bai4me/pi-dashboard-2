import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Lightbulb } from "lucide-react"

export default function KpisTab({ projectId }: { projectId: string }) {
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId, limit: 500 }),
  })
  const tasks: any[] = (tasksData as any)?.items || []

  const kpis = useMemo(() => {
    const total = tasks.length
    const done = tasks.filter((t: any) => t.status === "done").length
    const inProgress = tasks.filter((t: any) => t.status === "in_progress").length
    const review = tasks.filter((t: any) => t.status === "review").length
    const rueckfrage = tasks.filter((t: any) => t.status === "rueckfrage").length
    const warten = tasks.filter((t: any) => t.status === "warten").length
    const blocked = rueckfrage + warten
    const completionRate = total > 0 ? Math.round((done / total) * 100) : 0
    const avgIterations = total > 0 ? Math.round(tasks.reduce((s: number, t: any) => s + (t.iteration_count || 1), 0) / total) : 0
    const active = inProgress + review + rueckfrage + warten
    const target = 20
    const completionTarget = 80
    const iterTarget = 3
    const blockedTarget = 0
    const activeTarget = 5
    const health = total > 0 ? Math.max(0, Math.min(100, Math.round(((done * 100) / Math.max(1, total)) - (blocked * 10)))) : 0
    const healthTarget = 80

    return [
      { name: "Task Completion Rate", value: completionRate, target: completionTarget, unit: "%", category: "efficiency" },
      { name: "Avg Iterations per Task", value: avgIterations, target: iterTarget, unit: "", category: "quality" },
      { name: "Rückfragen + Warten", value: blocked, target: blockedTarget, unit: "", category: "speed" },
      { name: "Active Tasks", value: active, target: activeTarget, unit: "", category: "speed" },
      { name: "Total Tasks", value: total, target: target, unit: "", category: "efficiency" },
      { name: "Task Health Score", value: health, target: healthTarget, unit: "%", category: "quality" },
    ]
  }, [tasks])

  const underTarget = kpis.filter(k => k.value < k.target)

  return (
    <div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        {kpis.map((kpi) => {
          const pct = kpi.target > 0 ? (kpi.value / kpi.target) * 100 : 0
          const color = pct >= 80 ? "var(--color-hermes-accent)" : pct >= 50 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-danger)"
          return (
            <div key={kpi.name} className="stat-card">
              <div className="label">{kpi.name}</div>
              <div className="value" style={{ color }}>
                {kpi.value}{kpi.unit === "%" ? "%" : ""}
                <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 8, color: "var(--color-hermes-text-secondary)" }}>
                  / {kpi.target}{kpi.unit === "%" ? "%" : ""}
                </span>
              </div>
              <div style={{ marginTop: 6, height: 4, background: "var(--color-hermes-muted)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: color, borderRadius: 2 }} />
              </div>
              <div className="sublabel">{kpi.category}</div>
            </div>
          )
        })}
      </div>

      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
          <Lightbulb size={14} color="var(--color-hermes-accent-orange)" /> Efficiency Tips
        </h3>
        <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: 12, color: "var(--color-hermes-text-secondary)", lineHeight: 1.8 }}>
          {underTarget.length === 0 ? (
            <li>All KPIs are on target. Great job! Consider optimizing further for efficiency.</li>
          ) : (
            underTarget.map(kpi => (
              <li key={kpi.name}>{kpi.name}: {kpi.value}{kpi.unit === "%" ? "%" : ""}/{kpi.target}{kpi.unit === "%" ? "%" : ""} — needs improvement. Consider assigning sub-agents.</li>
            ))
          )}
        </ul>
      </div>
    </div>
  )
}
