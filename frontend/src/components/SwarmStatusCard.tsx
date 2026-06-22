// SwarmStatusCard.tsx — Zeigt aktiven Swarm-Status im Task-Detail-Panel
//
// User-Direktive 22.06.2026: Wenn ein Swarm laeuft, sollen alle Worker
// mit Status, Score und Progress sichtbar sein.

import { useQuery } from "@tanstack/react-query"
import { api } from "../api"

export interface SwarmWorker {
  id: string
  subagent_role: string
  variant: string
  weight: number
  status: "pending" | "running" | "completed" | "failed"
  output?: string
  cost_usd: number
  score?: number
  started_at?: string
  completed_at?: string
}

export interface SwarmRun {
  id: string
  task_id: string
  swarm_type: "single" | "parallel" | "competitive"
  status: "pending" | "running" | "completed" | "failed"
  merge_strategy: string
  total_cost_usd: number
  consensus_threshold: number
  auto_approve_threshold: number
  started_at?: string
  completed_at?: string
  result?: any
  workers: SwarmWorker[]
}

interface SwarmStatusCardProps {
  taskId: string
  style?: React.CSSProperties
}

const STATUS_COLORS: Record<string, string> = {
  pending:   "var(--color-hermes-text-secondary)",
  running:   "var(--color-hermes-accent-blue)",
  completed: "var(--color-hermes-accent)",
  failed:    "var(--color-hermes-danger)",
}

const STATUS_ICONS: Record<string, string> = {
  pending:   "⏳",
  running:   "🔄",
  completed: "✅",
  failed:    "❌",
}

const SWARM_TYPE_LABELS: Record<string, string> = {
  single:      "Single-Agent",
  parallel:    "Parallel Swarm",
  competitive: "Competitive Swarm",
}

/**
 * Karte mit allen laufenden/abgeschlossenen Swarms fuer einen Task.
 * Wird im Task-Detail-Panel angezeigt.
 */
export function SwarmStatusCard({ taskId, style }: SwarmStatusCardProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["swarms", taskId],
    queryFn: () => api.swarms?.listByTask(taskId) ?? Promise.resolve([]),
    enabled: !!taskId,
    refetchInterval: 5000,  // Live-Update alle 5s
    staleTime: 0,
  })

  const swarms: SwarmRun[] = (data as any) || []

  if (isLoading) {
    return (
      <div data-testid="swarm-status-card" data-loading="true" style={cardStyle(style)}>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
          Lade Swarm-Status...
        </div>
      </div>
    )
  }

  if (error) {
    return null
  }

  if (swarms.length === 0) {
    return null  // Kein Swarm fuer diesen Task
  }

  return (
    <div data-testid="swarm-status-card" data-count={swarms.length} style={cardStyle(style)}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 8,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--color-hermes-accent)" }}>
          🐝 Multi-Agent-Swarm ({swarms.length})
        </div>
      </div>
      {swarms.map((swarm) => (
        <SwarmItem key={swarm.id} swarm={swarm} />
      ))}
    </div>
  )
}

function SwarmItem({ swarm }: { swarm: SwarmRun }) {
  const statusColor = STATUS_COLORS[swarm.status] || "inherit"
  const statusIcon = STATUS_ICONS[swarm.status] || "?"
  const typeLabel = SWARM_TYPE_LABELS[swarm.swarm_type] || swarm.swarm_type
  const completedWorkers = swarm.workers.filter(w => w.status === "completed").length
  const totalWorkers = swarm.workers.length
  const consensusScore = swarm.result?.merged_output?.avg_score

  return (
    <div
      data-testid="swarm-item"
      data-swarm-id={swarm.id}
      data-status={swarm.status}
      style={{
        padding: 8,
        marginBottom: 6,
        background: "var(--color-hermes-bg)",
        border: `1px solid ${statusColor}`,
        borderRadius: 4,
        fontSize: 11,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontWeight: 600 }}>{typeLabel}</span>
        <span style={{ color: statusColor }}>
          {statusIcon} {swarm.status}
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
        <span className="badge badge-gray" style={{ fontSize: 9 }}>
          Merge: {swarm.merge_strategy}
        </span>
        <span className="badge badge-blue" style={{ fontSize: 9 }}>
          Workers: {completedWorkers}/{totalWorkers}
        </span>
        <span className="badge badge-orange" style={{ fontSize: 9 }}>
          ${swarm.total_cost_usd.toFixed(3)}
        </span>
        {consensusScore !== undefined && (
          <span
            className="badge"
            style={{
              fontSize: 9,
              background: consensusScore >= swarm.auto_approve_threshold
                ? "var(--color-hermes-accent)" : "var(--color-hermes-warning, #f59e0b)",
            }}
          >
            Score: {consensusScore.toFixed(1)}
          </span>
        )}
      </div>

      {/* Worker-Progress-Bars */}
      <div style={{ marginTop: 4 }}>
        {swarm.workers.map((w) => (
          <WorkerBar key={w.id} worker={w} />
        ))}
      </div>
    </div>
  )
}

function WorkerBar({ worker }: { worker: SwarmWorker }) {
  const color = STATUS_COLORS[worker.status]
  return (
    <div
      data-testid="worker-bar"
      data-worker-status={worker.status}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        fontSize: 10, marginBottom: 2,
      }}
    >
      <span style={{ minWidth: 80, color: "var(--color-hermes-text-secondary)" }}>
        {worker.subagent_role}/{worker.variant}
      </span>
      <div style={{
        flex: 1, height: 4, background: "var(--color-hermes-bg-secondary)",
        borderRadius: 2, overflow: "hidden",
      }}>
        <div style={{
          width: worker.status === "completed" ? "100%"
                : worker.status === "running" ? "60%"
                : worker.status === "failed" ? "100%"
                : "0%",
          height: "100%",
          background: color,
          transition: "width 0.3s ease",
        }} />
      </div>
      <span style={{ minWidth: 60, color, fontSize: 9 }}>
        {worker.status === "completed" && worker.score !== undefined && worker.score !== null
          ? `${worker.score.toFixed(0)}p` : worker.status}
      </span>
    </div>
  )
}

function cardStyle(extra?: React.CSSProperties): React.CSSProperties {
  return {
    padding: 10,
    background: "var(--color-hermes-bg-secondary)",
    border: "1px solid var(--color-hermes-border)",
    borderRadius: 6,
    ...extra,
  }
}