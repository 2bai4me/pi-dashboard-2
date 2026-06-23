// PlanningSection.tsx — Planung + Sub-Tasks fuer Task-Detail
// User-Direktive 23.06.2026 (Task 61ab3dfe26d3):
// - Planung-Section in Task-Detail (nach Beschreibung)
// - Pro SubTask eine eigene Planung + Agent + Session-ID
// - Sub-Tasks mit Kosten + Token-Anzeige

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Plus, Trash2, ListChecks, DollarSign, Zap } from "lucide-react"
import { api } from "../api"

interface PlanStep {
  step: string
  content: string
  agent?: string
}

interface SubTask {
  id: string
  parent_task_id: string
  title: string
  description?: string
  status: string
  assigned_subagent?: string
  plan?: { steps?: PlanStep[] }
  session_id?: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

interface PlanningSectionProps {
  taskId: string
  style?: React.CSSProperties
}

export function PlanningSection({ taskId, style }: PlanningSectionProps) {
  const qc = useQueryClient()
  const [isOpen, setIsOpen] = useState(true)
  const [showNewForm, setShowNewForm] = useState(false)

  const { data: subTasksData } = useQuery({
    queryKey: ["subtasks", taskId],
    queryFn: () => (api as any).subtasks?.list(taskId) ?? Promise.resolve([]),
    refetchInterval: 5000,
  })
  const subTasks: SubTask[] = (subTasksData as any) || []

  const totalCost = subTasks.reduce((s, st) => s + (st.cost_usd || 0), 0)
  const totalTokens = subTasks.reduce((s, st) => s + (st.tokens_in || 0) + (st.tokens_out || 0), 0)

  return (
    <div
      data-testid="planning-section"
      style={{
        background: "var(--color-hermes-bg-secondary)",
        border: "1px solid var(--color-hermes-border)",
        borderRadius: 6,
        marginTop: 8,
        ...style,
      }}
    >
      <div
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 12px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <ListChecks size={14} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600, fontSize: 13 }}>Planung</span>
          <span className="badge badge-gray" style={{ fontSize: 10 }}>
            {subTasks.length} Sub-Tasks
          </span>
          {totalCost > 0 && (
            <span className="badge badge-orange" style={{ fontSize: 10 }}>
              <DollarSign size={10} /> {totalCost.toFixed(4)}
            </span>
          )}
          {totalTokens > 0 && (
            <span className="badge badge-blue" style={{ fontSize: 10 }}>
              {totalTokens.toLocaleString()} tokens
            </span>
          )}
        </div>
        <button
          className="btn btn-sm btn-primary"
          style={{ fontSize: 10, padding: "2px 8px" }}
          onClick={(e) => { e.stopPropagation(); setShowNewForm(true) }}
        >
          <Plus size={10} /> Sub-Task
        </button>
      </div>

      {isOpen && (
        <div style={{ padding: "0 12px 12px 12px" }}>
          {showNewForm && (
            <NewSubTaskForm
              parentTaskId={taskId}
              onCancel={() => setShowNewForm(false)}
              onCreated={() => {
                setShowNewForm(false)
                qc.invalidateQueries({ queryKey: ["subtasks", taskId] })
              }}
            />
          )}

          {subTasks.length === 0 && !showNewForm && (
            <div style={{
              padding: 16,
              textAlign: "center",
              color: "var(--color-hermes-text-secondary)",
              fontSize: 12,
            }}>
              Noch keine Sub-Tasks. Klicke <strong>+ Sub-Task</strong> um eine neue Planung anzulegen.
            </div>
          )}

          {subTasks.map((st) => (
            <SubTaskCard
              key={st.id}
              subTask={st}
              onDelete={() => {
                if (confirm(`Sub-Task "${st.title}" loeschen?`)) {
                  (api as any).subtasks.delete(st.id)
                  qc.invalidateQueries({ queryKey: ["subtasks", taskId] })
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function NewSubTaskForm({ parentTaskId, onCancel, onCreated }: {
  parentTaskId: string
  onCancel: () => void
  onCreated: () => void
}) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [subagent, setSubagent] = useState("pi-coder")
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([
    { step: "Schritt 1", content: "", agent: "pi-coder" },
  ])

  const createMut = useMutation({
    mutationFn: async () => {
      const sessionId = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      return (api as any).subtasks.create({
        parent_task_id: parentTaskId,
        title,
        description,
        assigned_subagent: subagent,
        plan: { steps: planSteps.filter((s) => s.step && s.content) },
        session_id: sessionId,
      })
    },
    onSuccess: () => onCreated(),
  })

  return (
    <div
      data-testid="new-subtask-form"
      style={{
        background: "var(--color-hermes-bg)",
        border: "1px solid var(--color-hermes-border)",
        borderRadius: 4,
        padding: 10,
        marginBottom: 8,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <input
        className="input"
        placeholder="Titel des Sub-Tasks"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        autoFocus
      />
      <textarea
        className="input"
        placeholder="Beschreibung (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
      />
      <select className="input" value={subagent} onChange={(e) => setSubagent(e.target.value)}>
        <option value="pi-coder">pi-coder</option>
        <option value="pi-tester">pi-tester</option>
        <option value="pi-reviewer">pi-reviewer</option>
        <option value="pi-fixer">pi-fixer</option>
        <option value="pi-architect">pi-architect</option>
      </select>

      <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
        <strong>Planung (Stufen + Inhalte):</strong>
      </div>
      {planSteps.map((s, idx) => (
        <div key={idx} style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Stufe"
            value={s.step}
            onChange={(e) => {
              const next = [...planSteps]
              next[idx] = { ...next[idx], step: e.target.value }
              setPlanSteps(next)
            }}
          />
          <input
            className="input"
            style={{ flex: 2 }}
            placeholder="Inhalt"
            value={s.content}
            onChange={(e) => {
              const next = [...planSteps]
              next[idx] = { ...next[idx], content: e.target.value }
              setPlanSteps(next)
            }}
          />
          <button
            className="btn btn-sm"
            onClick={() => setPlanSteps(planSteps.filter((_, i) => i !== idx))}
            disabled={planSteps.length <= 1}
          >
            <Trash2 size={10} />
          </button>
        </div>
      ))}
      <button
        className="btn btn-sm"
        onClick={() => setPlanSteps([...planSteps, { step: "", content: "", agent: subagent }])}
      >
        <Plus size={10} /> Stufe
      </button>

      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button
          className="btn btn-sm btn-primary"
          disabled={!title.trim() || createMut.isPending}
          onClick={() => createMut.mutate()}
        >
          <Zap size={10} /> {createMut.isPending ? "Erstelle..." : "Erstellen + Sub-Agent starten"}
        </button>
        <button className="btn btn-sm" onClick={onCancel}>Abbrechen</button>
      </div>
    </div>
  )
}

function SubTaskCard({ subTask, onDelete }: {
  subTask: SubTask
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      data-testid="subtask-card"
      data-status={subTask.status}
      style={{
        background: "var(--color-hermes-bg)",
        border: "1px solid var(--color-hermes-border)",
        borderRadius: 4,
        padding: 8,
        marginBottom: 6,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div
          onClick={() => setExpanded(!expanded)}
          style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span style={{ fontWeight: 600, fontSize: 12 }}>{subTask.title}</span>
          <span className="badge badge-gray" style={{ fontSize: 9 }}>{subTask.status}</span>
          {subTask.assigned_subagent && (
            <span className="badge badge-blue" style={{ fontSize: 9 }}>{subTask.assigned_subagent}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
          {subTask.cost_usd > 0 && (
            <span data-testid="subtask-cost"><DollarSign size={10} /> {subTask.cost_usd.toFixed(4)}</span>
          )}
          {subTask.tokens_in + subTask.tokens_out > 0 && (
            <span data-testid="subtask-tokens">{(subTask.tokens_in + subTask.tokens_out).toLocaleString()} tokens</span>
          )}
          <button className="btn btn-sm" style={{ fontSize: 10, padding: "1px 4px" }} onClick={onDelete}>
            <Trash2 size={10} />
          </button>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 8, paddingLeft: 22 }}>
          {subTask.description && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
              {subTask.description}
            </div>
          )}
          {subTask.plan?.steps && subTask.plan.steps.length > 0 && (
            <div style={{ fontSize: 11 }}>
              <strong>Plan:</strong>
              <ol style={{ marginLeft: 16, marginTop: 4 }}>
                {subTask.plan.steps.map((s, i) => (
                  <li key={i}>
                    <strong>{s.step}</strong>
                    {s.agent && <span style={{ color: "var(--color-hermes-text-secondary)" }}> ({s.agent})</span>}
                    : {s.content}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {subTask.session_id && (
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
              Session: <code>{subTask.session_id}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}