import { useQuery } from "@tanstack/react-query"
import { api } from "../api"
import { Activity, Server, Cpu, HardDrive, Database, Zap, BarChart3, Users, Bot, Calendar, TrendingUp } from "lucide-react"
import { PageId } from "../components/PageId"
import { PAGE_IDS } from "../pageIds"
import { useMemo } from "react"

type DayCost = { day: string; tokens_in: number; tokens_out: number; cost_usd: number }
type ModelCost = { model: string; tokens_in: number; tokens_out: number; cost_usd: number; calls?: number }
type CostSummary = {
  days: number
  total: { tokens_in: number; tokens_out: number; cost_usd: number; calls: number }
  by_model: ModelCost[]
  by_day: DayCost[]
}
type AnalyticsSummary = {
  totals: { tasks: number; history_entries: number; token_usage_records: number; tokens_in: number; tokens_out: number; cost_usd: number }
  status_distribution: Record<string, number>
  cost_by_provider: Record<string, number>
}
type ActiveAgent = {
  type: string
  agent?: string
  role?: string
  session_id?: string | null
  task_id?: string | null
  status?: string
  details?: Record<string, any>
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`
  if (usd >= 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(6)}`
}

function providerFromModel(model: string): string {
  // Extract provider from "provider/model" or fallback
  if (model.includes("/")) return model.split("/")[0]
  return model
}

function aggregateByProviderByPeriod(
  byModel: ModelCost[],
  byDay: DayCost[] | undefined,
  periodFn: (day: string) => string,
): Record<string, { tokens_in: number; tokens_out: number; cost_usd: number; calls: number; label: string }> {
  // Aggregate by provider for the given period function
  const result: Record<string, any> = {}
  if (byDay && byDay.length) {
    // Use by_day if available, but we need to attribute to provider. Since by_day doesn't have provider,
    // we approximate by using the share from by_model. Simpler: aggregate by_day per provider proportionally.
    // Better: ask backend for by_provider_by_day endpoint, but for now we approximate.
    // For the MVP, we show by_day with the *total* and label it as "All Providers".
    // We will sum the totals across all days and group by period.
    for (const d of byDay) {
      const label = periodFn(d.day)
      if (!result[label]) {
        result[label] = { tokens_in: 0, tokens_out: 0, cost_usd: 0, calls: 0, label }
      }
      result[label].tokens_in += d.tokens_in
      result[label].tokens_out += d.tokens_out
      result[label].cost_usd += d.cost_usd
    }
  } else if (byModel) {
    for (const m of byModel) {
      const provider = providerFromModel(m.model)
      if (!result[provider]) {
        result[provider] = { tokens_in: 0, tokens_out: 0, cost_usd: 0, calls: 0, label: provider }
      }
      result[provider].tokens_in += m.tokens_in
      result[provider].tokens_out += m.tokens_out
      result[provider].cost_usd += m.cost_usd
      result[provider].calls += m.calls || 0
    }
  }
  return result
}

function last7Days(): string[] {
  const out: string[] = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    out.push(d.toISOString().slice(0, 10))
  }
  return out
}

function last6Months(): string[] {
  const out: string[] = []
  const now = new Date()
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now)
    d.setMonth(d.getMonth() - i, 1)
    out.push(d.toISOString().slice(0, 7)) // YYYY-MM
  }
  return out
}

export default function Overview() {
  const { data: analytics } = useQuery({ queryKey: ["analytics"], queryFn: () => api.getAnalytics() as Promise<AnalyticsSummary> })
  const { data: cost30 } = useQuery({ queryKey: ["cost30"], queryFn: () => api.getCostSummary(30) as Promise<CostSummary> })
  const { data: cost180 } = useQuery({ queryKey: ["cost180"], queryFn: () => api.getCostSummary(180) as Promise<CostSummary> })
  const { data: gateway } = useQuery({ queryKey: ["gateway"], queryFn: () => api.getGatewayStatus() })
  const { data: activeAgentsData } = useQuery({ queryKey: ["active-agents"], queryFn: () => api.operators.listActiveAgents(), refetchInterval: 15000 })
  const { data: projectsData } = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() as Promise<{ items: any[]; total: number }> })

  // --- Derived: Projects, Tasks counts ---
  const projectCount = projectsData?.total ?? 0
  const taskCount = analytics?.totals?.tasks ?? 0
  const tokensIn = analytics?.totals?.tokens_in ?? 0
  const tokensOut = analytics?.totals?.tokens_out ?? 0
  const totalCost = analytics?.totals?.cost_usd ?? 0

  // --- Status distribution ---
  const statusDist = analytics?.status_distribution || {}
  const statusEntries = Object.entries(statusDist).sort((a, b) => b[1] - a[1])

  // --- Provider totals (all-time) ---
  const costByProvider = analytics?.cost_by_provider || {}

  // --- 7 days table (one row per provider per day would be ideal; we do per-provider totals last 7 days) ---
  // We use the last 7 days from cost30.by_day
  const days7 = useMemo(() => last7Days(), [])
  const last7ByDay: Record<string, DayCost> = useMemo(() => {
    const m: Record<string, DayCost> = {}
    if (cost30?.by_day) {
      for (const d of cost30.by_day) {
        if (days7.includes(d.day)) m[d.day] = d
      }
    }
    return m
  }, [cost30, days7])

  // For 7-day by-provider: we have by_model (all-time), but for 7 days we approximate by prorating
  // the 7-day total by the all-time model shares.
  const last7ByProvider = useMemo(() => {
    const last7TokensIn = Object.values(last7ByDay).reduce((a, b) => a + b.tokens_in, 0)
    const last7TokensOut = Object.values(last7ByDay).reduce((a, b) => a + b.tokens_out, 0)
    const last7Cost = Object.values(last7ByDay).reduce((a, b) => a + b.cost_usd, 0)
    const totalTokensIn = cost30?.total?.tokens_in || 0
    const totalTokensOut = cost30?.total?.tokens_out || 0
    const totalCost = cost30?.total?.cost_usd || 0
    const ratio = (n: number) => (totalCost > 0 ? n / totalCost : 0)
    const result: Record<string, { tokens_in: number; tokens_out: number; cost_usd: number }> = {}
    if (cost30?.by_model) {
      for (const m of cost30.by_model) {
        const provider = providerFromModel(m.model)
        if (!result[provider]) result[provider] = { tokens_in: 0, tokens_out: 0, cost_usd: 0 }
        const r = ratio(m.cost_usd)
        result[provider].tokens_in += Math.round(m.tokens_in * r)
        result[provider].tokens_out += Math.round(m.tokens_out * r)
        result[provider].cost_usd += m.cost_usd * r
      }
    }
    // Scale to match actual 7-day totals
    const sumCost = Object.values(result).reduce((a, b) => a + b.cost_usd, 0)
    if (sumCost > 0 && last7Cost > 0) {
      const scale = last7Cost / sumCost
      for (const k of Object.keys(result)) {
        result[k].cost_usd = result[k].cost_usd * scale
      }
    }
    return result
  }, [cost30, last7ByDay])

  // --- 6 months table (one row per provider per month) ---
  // We aggregate by_day for 6 months, grouped by month, and prorate by model share.
  const months6 = useMemo(() => last6Months(), [])
  const last6ByMonth: Record<string, DayCost> = useMemo(() => {
    const m: Record<string, DayCost> = {}
    if (cost180?.by_day) {
      for (const d of cost180.by_day) {
        const month = d.day.slice(0, 7)
        if (months6.includes(month)) {
          if (!m[month]) m[month] = { day: month, tokens_in: 0, tokens_out: 0, cost_usd: 0 }
          m[month].tokens_in += d.tokens_in
          m[month].tokens_out += d.tokens_out
          m[month].cost_usd += d.cost_usd
        }
      }
    }
    return m
  }, [cost180, months6])

  const last6ByProvider = useMemo(() => {
    const totalCost = cost180?.total?.cost_usd || 0
    const totalCostOf6Months = Object.values(last6ByMonth).reduce((a, b) => a + b.cost_usd, 0)
    const ratio = (n: number) => (totalCost > 0 ? n / totalCost : 0)
    const result: Record<string, { tokens_in: number; tokens_out: number; cost_usd: number }> = {}
    if (cost180?.by_model) {
      for (const m of cost180.by_model) {
        const provider = providerFromModel(m.model)
        if (!result[provider]) result[provider] = { tokens_in: 0, tokens_out: 0, cost_usd: 0 }
        const r = ratio(m.cost_usd)
        result[provider].tokens_in += Math.round(m.tokens_in * r)
        result[provider].tokens_out += Math.round(m.tokens_out * r)
        result[provider].cost_usd += m.cost_usd * r
      }
    }
    // Scale to actual 6-month totals
    const sumCost = Object.values(result).reduce((a, b) => a + b.cost_usd, 0)
    if (sumCost > 0 && totalCostOf6Months > 0) {
      const scale = totalCostOf6Months / sumCost
      for (const k of Object.keys(result)) {
        result[k].cost_usd = result[k].cost_usd * scale
      }
    }
    return result
  }, [cost180, last6ByMonth])

  // --- Active agents ---
  const activeAgents: ActiveAgent[] = (activeAgentsData as any)?.items || []
  const activeByType: Record<string, number> = (activeAgentsData as any)?.by_type || {}

  return (
    <div>
      <div className="page-header">
        <h1>Übersicht</h1>
        <PageId id={PAGE_IDS.INDEX} />
        <p>Projekte · Tasks · Token · Kosten · Aktive Agenten</p>
      </div>

      {/* Top stats */}
      <div className="card-grid">
        <div className="stat-card">
          <span className="label"><HardDrive size={11} style={{ display: "inline", marginRight: 4 }} /> Projekte</span>
          <span className="value">{projectCount}</span>
          <span className="sublabel">{projectsData?.items?.filter((p: any) => p.status === "active").length ?? 0} aktiv</span>
        </div>
        <div className="stat-card">
          <span className="label"><Activity size={11} style={{ display: "inline", marginRight: 4 }} /> Tasks</span>
          <span className="value">{taskCount}</span>
          <span className="sublabel">{statusDist["done"] ?? 0} done · {statusDist["in_progress"] ?? 0} in_progress</span>
        </div>
        <div className="stat-card">
          <span className="label"><Zap size={11} style={{ display: "inline", marginRight: 4 }} /> Token Total</span>
          <span className="value">{formatNumber(tokensIn + tokensOut)}</span>
          <span className="sublabel">⬇ {formatNumber(tokensIn)} in · ⬆ {formatNumber(tokensOut)} out</span>
        </div>
        <div className="stat-card">
          <span className="label"><TrendingUp size={11} style={{ display: "inline", marginRight: 4 }} /> Gesamtkosten</span>
          <span className="value" style={{ color: "var(--color-hermes-danger)" }}>{formatCost(totalCost)}</span>
          <span className="sublabel">{analytics?.totals?.token_usage_records ?? 0} Calls</span>
        </div>
      </div>

      {/* System health */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Server size={16} /> System-Health
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <div>
            <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>Backend</div>
            <div style={{ color: "var(--color-hermes-accent)", fontWeight: 600 }}>Online · 127.0.0.1:9220</div>
          </div>
          <div>
            <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>Datenbank</div>
            <div style={{ color: "var(--color-hermes-accent)", fontWeight: 600 }}>SQLite · v2.0-rc</div>
          </div>
          <div>
            <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>PI Agent</div>
            <div style={{ fontWeight: 600 }}>{(gateway as any)?.pi?.version || "—"} · {(gateway as any)?.pi?.running ? "running" : "stopped"}</div>
          </div>
          <div>
            <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>Ollama</div>
            <div style={{ fontWeight: 600 }}>{(gateway as any)?.ollama?.running ? `${(gateway as any).ollama.model_count} models` : "—"}</div>
          </div>
        </div>
      </div>

      {/* Status distribution */}
      {statusEntries.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <BarChart3 size={16} /> Task-Status-Verteilung
          </h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {statusEntries.map(([status, count]) => {
              const pct = taskCount > 0 ? (count / taskCount) * 100 : 0
              const colors: Record<string, string> = {
                done: "var(--color-hermes-accent)",
                in_progress: "var(--color-hermes-accent-orange)",
                rueckfrage: "var(--color-hermes-warning)",
                triage: "var(--color-hermes-text-secondary)",
                failed: "var(--color-hermes-danger)",
                cancelled: "var(--color-hermes-text-secondary)",
                todo: "var(--color-hermes-accent-blue)",
              }
              const color = colors[status] || "var(--color-hermes-text-secondary)"
              return (
                <div key={status} style={{
                  padding: "6px 12px",
                  border: `1px solid ${color}`,
                  borderRadius: 4,
                  minWidth: 100,
                }}>
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{status}</div>
                  <div style={{ fontSize: 18, fontWeight: 600, color }}>{count}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{pct.toFixed(1)}%</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Active agents & subagents */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Users size={16} /> Aktive Agenten &amp; Subagenten
        </h3>
        {Object.keys(activeByType).length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
            {Object.entries(activeByType).map(([type, count]) => (
              <div key={type} style={{
                padding: "4px 10px",
                background: "var(--color-hermes-bg-secondary)",
                borderRadius: 4,
                fontSize: 12,
              }}>
                <Bot size={10} style={{ display: "inline", marginRight: 4 }} />
                <strong>{type}</strong>: {count}
              </div>
            ))}
          </div>
        )}
        {activeAgents.length === 0 ? (
          <p style={{ color: "var(--color-hermes-text-secondary)", margin: 0 }}>
            Keine aktiven Agenten gerade.
          </p>
        ) : (
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Typ</th>
                <th>Agent</th>
                <th>Rolle</th>
                <th>Session-ID</th>
                <th>Task</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {activeAgents.map((a, i) => (
                <tr key={i}>
                  <td><code>{a.type}</code></td>
                  <td>{a.agent || "—"}</td>
                  <td>{a.role || "—"}</td>
                  <td style={{ fontSize: 11, fontFamily: "monospace" }}>{a.session_id || "—"}</td>
                  <td style={{ fontSize: 11, fontFamily: "monospace" }}>{a.task_id || "—"}</td>
                  <td>
                    <span style={{
                      padding: "2px 6px",
                      borderRadius: 3,
                      fontSize: 11,
                      background: a.status === "running" ? "var(--color-hermes-accent)" : "var(--color-hermes-bg-secondary)",
                      color: a.status === "running" ? "white" : "var(--color-hermes-text-secondary)",
                    }}>
                      {a.status || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 7 days: Token + Costs per Provider */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Calendar size={16} /> Token &amp; Kosten je Provider — letzte 7 Tage
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%", minWidth: 600 }}>
            <thead>
              <tr>
                <th>Provider</th>
                {days7.map((d) => (
                  <th key={d} style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      {new Date(d).toLocaleDateString("de-DE", { weekday: "short" })}
                    </div>
                    {d.slice(5)}
                  </th>
                ))}
                <th style={{ textAlign: "right" }}>Σ Token</th>
                <th style={{ textAlign: "right" }}>Σ Kosten</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(last7ByProvider).length === 0 ? (
                <tr><td colSpan={days7.length + 3} style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
                  Keine Daten für die letzten 7 Tage.
                </td></tr>
              ) : (
                Object.entries(last7ByProvider).sort((a, b) => b[1].cost_usd - a[1].cost_usd).map(([provider, totals]) => {
                  // Distribute the totals across days using each day's share of the week
                  const totalWeekCost = Object.values(last7ByDay).reduce((a, b) => a + b.cost_usd, 0) || 1
                  return (
                    <tr key={provider}>
                      <td><strong>{provider}</strong></td>
                      {days7.map((d) => {
                        const day = last7ByDay[d]
                        if (!day) return <td key={d} style={{ textAlign: "right", color: "var(--color-hermes-text-secondary)" }}>—</td>
                        const dayShare = day.cost_usd / totalWeekCost
                        const dayCost = totals.cost_usd * dayShare
                        return (
                          <td key={d} style={{ textAlign: "right", fontSize: 11 }}>
                            {dayCost > 0 ? formatCost(dayCost) : "—"}
                          </td>
                        )
                      })}
                      <td style={{ textAlign: "right" }}>{formatNumber(totals.tokens_in + totals.tokens_out)}</td>
                      <td style={{ textAlign: "right", color: "var(--color-hermes-danger)" }}>{formatCost(totals.cost_usd)}</td>
                    </tr>
                  )
                })
              )}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: "2px solid var(--color-hermes-border)" }}>
                <td><strong>Total</strong></td>
                {days7.map((d) => {
                  const day = last7ByDay[d]
                  return (
                    <td key={d} style={{ textAlign: "right", fontSize: 11, fontWeight: 600 }}>
                      {day ? formatCost(day.cost_usd) : "—"}
                    </td>
                  )
                })}
                <td style={{ textAlign: "right", fontWeight: 600 }}>
                  {formatNumber(Object.values(last7ByDay).reduce((a, b) => a + b.tokens_in + b.tokens_out, 0))}
                </td>
                <td style={{ textAlign: "right", fontWeight: 600, color: "var(--color-hermes-danger)" }}>
                  {formatCost(Object.values(last7ByDay).reduce((a, b) => a + b.cost_usd, 0))}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 8, marginBottom: 0 }}>
          Hinweis: Provider-Verteilung wird aus dem Gesamt-Modell-Verhältnis proratiert (Backend liefert by_day ohne Provider).
        </p>
      </div>

      {/* 6 months: Token + Costs per Provider */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Calendar size={16} /> Token &amp; Kosten je Provider — letzte 6 Monate
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%", minWidth: 600 }}>
            <thead>
              <tr>
                <th>Provider</th>
                {months6.map((m) => (
                  <th key={m} style={{ textAlign: "right" }}>{m}</th>
                ))}
                <th style={{ textAlign: "right" }}>Σ Token</th>
                <th style={{ textAlign: "right" }}>Σ Kosten</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(last6ByProvider).length === 0 ? (
                <tr><td colSpan={months6.length + 3} style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
                  Keine Daten für die letzten 6 Monate.
                </td></tr>
              ) : (
                Object.entries(last6ByProvider).sort((a, b) => b[1].cost_usd - a[1].cost_usd).map(([provider, totals]) => {
                  const total6Cost = Object.values(last6ByMonth).reduce((a, b) => a + b.cost_usd, 0) || 1
                  return (
                    <tr key={provider}>
                      <td><strong>{provider}</strong></td>
                      {months6.map((m) => {
                        const month = last6ByMonth[m]
                        if (!month) return <td key={m} style={{ textAlign: "right", color: "var(--color-hermes-text-secondary)" }}>—</td>
                        const monthShare = month.cost_usd / total6Cost
                        const monthCost = totals.cost_usd * monthShare
                        return (
                          <td key={m} style={{ textAlign: "right", fontSize: 11 }}>
                            {monthCost > 0 ? formatCost(monthCost) : "—"}
                          </td>
                        )
                      })}
                      <td style={{ textAlign: "right" }}>{formatNumber(totals.tokens_in + totals.tokens_out)}</td>
                      <td style={{ textAlign: "right", color: "var(--color-hermes-danger)" }}>{formatCost(totals.cost_usd)}</td>
                    </tr>
                  )
                })
              )}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: "2px solid var(--color-hermes-border)" }}>
                <td><strong>Total</strong></td>
                {months6.map((m) => {
                  const month = last6ByMonth[m]
                  return (
                    <td key={m} style={{ textAlign: "right", fontSize: 11, fontWeight: 600 }}>
                      {month ? formatCost(month.cost_usd) : "—"}
                    </td>
                  )
                })}
                <td style={{ textAlign: "right", fontWeight: 600 }}>
                  {formatNumber(Object.values(last6ByMonth).reduce((a, b) => a + b.tokens_in + b.tokens_out, 0))}
                </td>
                <td style={{ textAlign: "right", fontWeight: 600, color: "var(--color-hermes-danger)" }}>
                  {formatCost(Object.values(last6ByMonth).reduce((a, b) => a + b.cost_usd, 0))}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 8, marginBottom: 0 }}>
          Hinweis: Provider-Verteilung proratiert (siehe 7-Tage-Tabelle).
        </p>
      </div>
    </div>
  )
}
