// TaskDetailPanel — Wiederverwendbare Sidebar-Komponente
// Wird in Kanban.tsx (Projekte/Board/Tasks) und Cost.tsx (Performance) verwendet.
// User-Direktive 16.06.2026: Einheitliche Sidebar in allen Views.
import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import {
  X, Flame, Hash, CheckCircle2, ChevronDown, ChevronRight,
  RotateCcw, Trash2,
} from "lucide-react"
import { CioTriageSection } from "./CioTriageSection"
import { SpeakButton } from "./SpeakButton"
import { PlanningSection } from "./PlanningSection"

export function TaskDetailPanel({ taskId, projectName, onClose }: { taskId: string; projectName: string; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: task } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId),
  })
  const [copied, setCopied] = useState(false)
  const [priority, setPriority] = useState(task?.priority || 0)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  // Welche Accordion-Sections sind offen (alle standardmaessig zu, ausser 'meta')
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    meta: true,        // Status/Prio/Role (default offen — wichtigste Info)
    description: true, // Beschreibung
    criteria: true,    // Erfolgskriterien (default offen — wichtig fuer den Worker)
    subtasks: true,    // Sub-Tasks sind zentral, default offen
    history: false,
    action: true,      // Action-Bar (Buttons) immer offen
    danger: false,     // Loesch-Button separat, default zu
  })

  function toggleSection(key: string) {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  // Task-History
  const { data: historyData } = useQuery({
    queryKey: ["task-history", taskId],
    queryFn: () => api.getTaskHistory(taskId),
    enabled: openSections.history, // nur laden wenn aufgeklappt
  })

  useEffect(() => {
    if (task?.priority !== undefined) setPriority(task.priority)
  }, [task?.priority])

  const priorityMut = useMutation({
    mutationFn: (p: number) => api.setTaskPriority(taskId, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })

  // === Status-Wechsel (User-Direktive 17.06.2026: Fallback fuer Drag&Drop) ===
  const [showMoveMenu, setShowMoveMenu] = useState(false)
  const statusMut = useMutation({
    mutationFn: (newStatus: string) => api.setTaskStatus(taskId, newStatus),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      qc.invalidateQueries({ queryKey: ["tasks"] })
      qc.invalidateQueries({ queryKey: ["agent-questions"] })
    },
  })
  const STATUSES = [
    { key: "triage", label: "Triage" },
    { key: "todo", label: "GO" },
    { key: "in_progress", label: "In Progress" },
    { key: "review", label: "Review" },
    { key: "done", label: "Done" },
    { key: "rueckfrage", label: "Rückfrage" },
  ]

  const aggregateMut = useMutation({
    mutationFn: () => api.aggregateSubtasks(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })

  const deleteMut = useMutation({
    mutationFn: () => api.wfReopen(taskId, "CEO", "Task zurueck in Triage — Standard-Workflow durchlaufen", true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] })
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      onClose()
    },
  })

  function copyId() {
    if (task?.id) {
      navigator.clipboard.writeText(task.id)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    }
  }

  if (!task) {
    return (
      <div className="detail-panel">
        <div className="detail-panel-header">
          <span style={{ color: "var(--color-hermes-text-secondary)" }}>Lade…</span>
          <button className="btn btn-sm" onClick={onClose}><X size={12} /></button>
        </div>
      </div>
    )
  }

  const successCriteria = task.success_criteria || []
  const subtasks: any[] = task.subtasks || []

  return (
    <div className="detail-panel">
      {/* === HEADER (ganz oben) mit Task-ID prominent === */}
      <div className="detail-panel-header" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {/* Top: Task-ID (prominent) + Close-Button */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            className={`id-badge id-badge-prominent ${copied ? "id-badge-copied" : ""}`}
            onClick={copyId}
            style={{ fontSize: 13, padding: "3px 10px", fontWeight: 600, letterSpacing: "0.5px" }}
            title="Task-ID · Klick zum Kopieren"
          >
            {task.id}
          </span>
          <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", flex: 1 }}>
            {copied ? "✓ kopiert!" : "Task-ID · Klick zum Kopieren"}
          </span>
          <button className="btn btn-sm" onClick={onClose} title="Schliessen"><X size={12} /></button>
        </div>
        {/* Bottom: Status + Prio + Aktionen */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="badge badge-orange">{task.status_display || task.status}</span>
          <Flame size={12} color="var(--color-hermes-accent-orange)" />
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Prio {task.priority}</span>
          {task.assigned_role && (
            <>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>·</span>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>💻 {task.assigned_role}</span>
            </>
          )}
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-sm btn-danger"
            onClick={() => setShowDeleteConfirm(true)}
            title="Task wieder in Triage (Standard-Workflow durchlaufen)"
            aria-label="Task wieder in Triage"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      <div className="detail-panel-body">
        {/* === CIO Triage Section (Schritt 0) — User-Direktive 16.06.2026 === */}
        <CioTriageSection taskId={taskId} task={task} />

        <h2 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px" }}>{task.title}</h2>
        <p style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, margin: "0 0 12px" }}>
          Projekt: {projectName}
        </p>

        {/* Accordion-Section 1: Meta (Status, Prio, Role) */}
        <AccordionSection
          open={openSections.meta}
          onToggle={() => toggleSection("meta")}
          icon="📋"
          title="Meta"
          summary={task.assigned_role ? `${task.assigned_role} · Prio ${priority}` : `Prio ${priority}`}
          rightSlot={
            <div onClick={(e) => e.stopPropagation()}>
              <SpeakButton
                text={`Task ${task.title}. Status ${task.status_display || task.status}. Priorität ${priority}${task.assigned_role ? `. Zugewiesen an ${task.assigned_role}` : ""}`}
                label="Meta vorlesen"
              />
            </div>
          }
        >
          {task.assigned_role && (
            <div style={{ marginBottom: 10 }}>
              <span className="badge badge-blue">💻 {task.assigned_role}</span>
            </div>
          )}
          <h4 style={{ margin: "0 0 6px", fontSize: 12 }}>🔥 Priorität: {priority}</h4>
          <input
            type="range"
            min={0}
            max={100}
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            onMouseUp={() => priorityMut.mutate(priority)}
            onTouchEnd={() => priorityMut.mutate(priority)}
            className="priority-slider"
          />
          <div className="priority-marks">
            <span>0 niedrig</span>
            <span>50 mittel</span>
            <span>75 hoch</span>
            <span>100 🚨 NOTFALL</span>
          </div>
        </AccordionSection>

        {/* Accordion-Section: SOP-Status (User-Direktive 18.06.2026) */}
        <SopStatusSection taskId={task.id} />

        {/* Accordion-Section 2: Description */}
        {task.description && (
          <AccordionSection
            open={openSections.description}
            onToggle={() => toggleSection("description")}
            icon="📝"
            title="Beschreibung"
            rightSlot={
              <div onClick={(e) => e.stopPropagation()}>
                <SpeakButton text={task.description} label="Beschreibung vorlesen" showLabel={false} />
              </div>
            }
          >
            <div className="description-box">{task.description}</div>
          </AccordionSection>
        )}

        {/* User-Direktive 23.06.2026: Planung-Section nach Beschreibung */}
        <PlanningSection taskId={task.id} />

        {/* Accordion-Section 3: Success Criteria (immer sichtbar, auch bei 0 Kriterien) */}
        <AccordionSection
          open={openSections.criteria}
          onToggle={() => toggleSection("criteria")}
          icon={<CheckCircle2 size={12} />}
          title={`Success Criteria (${successCriteria.length}${successCriteria.length === 0 ? ", fehlen" : ""})`}
          rightSlot={
            successCriteria.length > 0 ? (
              <div onClick={(e) => e.stopPropagation()}>
                <SpeakButton
                  text={successCriteria.map((sc: any) => typeof sc === "string" ? sc : sc.text || JSON.stringify(sc)).join(". ")}
                  label="Alle Criteria vorlesen"
                />
              </div>
            ) : undefined
          }
        >
          {successCriteria.length > 0 ? (
            <div className="success-criteria">
              {successCriteria.map((sc: any, i: number) => (
                <div key={i} className="success-criterion">
                  <CheckCircle2 size={12} color="var(--color-hermes-accent)" className="success-criterion-check" />
                  <span style={{ flex: 1 }}>{typeof sc === "string" ? sc : sc.text || JSON.stringify(sc)}</span>
                  <span onClick={(e) => e.stopPropagation()}>
                    <SpeakButton text={typeof sc === "string" ? sc : sc.text || JSON.stringify(sc)} />
                  </span>
                </div>
              ))}
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #999)", marginTop: 8, fontStyle: "italic" }}>
                Maximal 1-3 Kriterien empfohlen (Worker wird sonst ueberfordert).
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary, #999)", padding: 8, textAlign: "center", fontStyle: "italic" }}>
              Keine Kriterien definiert. Erstelle einen neuen Task mit KI-Unterstuetzung,
              um automatisch 1-3 testbare Kriterien zu generieren.
            </div>
          )}
        </AccordionSection>

        {/* Accordion-Section 4: Sub-Tasks */}
        <AccordionSection
          open={openSections.subtasks}
          onToggle={() => toggleSection("subtasks")}
          icon="↓"
          title={`Sub-Tasks (${subtasks.length || "—"})`}
          rightSlot={
            <button
              className="btn btn-sm"
              onClick={(e) => { e.stopPropagation(); aggregateMut.mutate() }}
              disabled={aggregateMut.isPending}
            >
              💻 Aggregieren
            </button>
          }
        >
          {subtasks.length > 0 ? (
            <div>
              {subtasks.slice(0, 5).map((s: any) => (
                <div key={s.id} className="subtask-item">
                  <Hash size={10} color="var(--color-hermes-text-secondary)" />
                  <span className="id-badge id-badge-child">{s.id.slice(0, 6)}</span>
                  <span style={{ flex: 1, fontSize: 11 }}>{s.title}</span>
                  <span className="badge badge-gray" style={{ fontSize: 9 }}>{s.status}</span>
                </div>
              ))}
              {subtasks.length > 5 && (
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 4, textAlign: "center" }}>
                  + {subtasks.length - 5} weitere...
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>
              Keine Sub-Tasks vorhanden.
            </div>
          )}
        </AccordionSection>

        {/* Accordion-Section 5: History */}
        <AccordionSection
          open={openSections.history}
          onToggle={() => toggleSection("history")}
          icon="🕐"
          title={`History (${historyData?.history?.length ?? "—"})`}
          rightSlot={
            historyData?.history && historyData.history.length > 0 ? (
              <div onClick={(e) => e.stopPropagation()}>
                <SpeakButton
                  text={historyData.history.slice(0, 20).map((h: any) => `${h.event} von ${h.agent || "system"}`).join(". ")}
                  label="History vorlesen"
                />
              </div>
            ) : null
          }
        >
          {historyData?.history && historyData.history.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {historyData.history.slice(0, 20).map((h: any) => (
                <div key={h.id} style={{ fontSize: 11, padding: "6px 8px", background: "var(--color-hermes-muted)", borderRadius: 4, borderLeft: "2px solid var(--color-hermes-accent-blue)" }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontWeight: 600 }}>{h.event}</span>
                    <span style={{ color: "var(--color-hermes-text-secondary)" }}>· {h.agent || "system"}</span>
                    <span style={{ color: "var(--color-hermes-text-secondary)", marginLeft: "auto" }}>
                      {h.ts ? new Date(h.ts).toLocaleString("de-DE") : ""}
                    </span>
                  </div>
                  {h.model && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Model: {h.model}</div>
                  )}
                  {(h.tokens_in > 0 || h.tokens_out > 0) && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      Tokens: {h.tokens_in} in / {h.tokens_out} out · ${h.cost_usd?.toFixed(4) ?? "0.0000"}
                    </div>
                  )}
                  {/* User-Direktive 18.06.2026: details_mapped zeigt 'GO' statt 'todo' */}
                  {h.details_mapped && Object.keys(h.details_mapped).length > 0 && (
                    <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                      {Object.entries(h.details_mapped)
                        .filter(([k, v]) => ["from", "to", "from_status", "to_status", "old_status", "new_status"].includes(k))
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", fontStyle: "italic" }}>
              {openSections.history ? "Keine History-Einträge." : "History laden..."}
            </div>
          )}
        </AccordionSection>

        {/* Accordion-Section 6: Workflow-Action-Bar (default offen) */}
        <AccordionSection
          open={openSections.action}
          onToggle={() => toggleSection("action")}
          icon="⚡"
          title="Aktionen"
        >
          {/* ─── Status-Verschieben (User-Direktive 17.06.2026: Fallback fuer Drag&Drop) ─── */}
          <div style={{ marginBottom: 14, padding: 10, border: "1px solid var(--color-hermes-border, #333)", borderRadius: 6, background: "rgba(124,58,237,0.05)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary, #999)", fontWeight: 600, textTransform: "uppercase" }}>
                In Spalte verschieben
              </span>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #666)", marginLeft: "auto" }}>
                Aktuell: <code style={{ background: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 3 }}>{task.status_display || task.status}</code>
              </span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {STATUSES.filter((s) => s.key !== task.status).map((s) => (
                <button
                  key={s.key}
                  className="btn btn-sm"
                  disabled={statusMut.isPending}
                  onClick={() => {
                    if (confirm(`Task wirklich nach "${s.label}" verschieben?\n\nBei "triage" wird die Standard-SOP neu gestartet.`)) {
                      statusMut.mutate(s.key)
                    }
                  }}
                  style={{ fontSize: 10, padding: "3px 8px" }}
                  title={`Verschieben nach ${s.label}`}
                >
                  → {s.label}
                </button>
              ))}
            </div>
            {statusMut.isPending && (
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary, #999)", marginTop: 4 }}>
                Verschiebe...
              </div>
            )}
            {statusMut.isError && (
              <div style={{ fontSize: 10, color: "#dc2626", marginTop: 4 }}>
                ⚠ Fehler beim Verschieben. Bitte erneut versuchen.
              </div>
            )}
          </div>

          {/* ─── Standard-Workflow Action Bar (je nach Status) ─── */}
          <WorkflowActionBar taskId={taskId} status={task.status} qc={qc} />
        </AccordionSection>

        {/* Accordion-Section 7: Danger Zone (Loeschen) */}
        <AccordionSection
          open={openSections.danger || showDeleteConfirm}
          onToggle={() => toggleSection("danger")}
          icon="⚠️"
          title="Danger Zone"
          tone="danger"
        >
          {showDeleteConfirm ? (
            <div style={{ padding: 10, background: "rgba(255, 166, 43, 0.08)", border: "1px solid var(--color-hermes-accent-orange)", borderRadius: 6 }}>
              <div style={{ fontSize: 12, marginBottom: 8, color: "var(--color-hermes-accent-orange)", fontWeight: 600 }}>
                ↺ Task wieder in Triage?
              </div>
              <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 10 }}>
                "<strong>{task.title}</strong>" wird NICHT gelöscht, sondern zurück in die <strong>Triage</strong> gestellt.
                Der Auto-Operator bewertet ihn erneut nach dem <strong>Standard-Workflow</strong>.
                History bleibt erhalten, Iteration-Counter wird zurückgesetzt.
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => deleteMut.mutate()}
                  disabled={deleteMut.isPending}
                >
                  {deleteMut.isPending ? "Wieder in Triage..." : "Ja, in Triage stellen"}
                </button>
                <button
                  className="btn btn-sm"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleteMut.isPending}
                >
                  Abbrechen
                </button>
              </div>
            </div>
          ) : (
            <button
              className="btn btn-sm btn-danger"
              onClick={() => setShowDeleteConfirm(true)}
            >
              <Trash2 size={12} /> Task wieder in Triage
            </button>
          )}
        </AccordionSection>
      </div>
    </div>
  )
}

// ─────────────── Accordion Section ───────────────
function AccordionSection({
  open,
  onToggle,
  icon,
  title,
  summary,
  rightSlot,
  tone,
  children,
}: {
  open: boolean
  onToggle: () => void
  icon?: React.ReactNode
  title: string
  summary?: string
  rightSlot?: React.ReactNode
  tone?: "default" | "danger"
  children: React.ReactNode
}) {
  const isDanger = tone === "danger"
  return (
    <div
      className="detail-panel-section"
      style={{
        borderLeft: `3px solid ${isDanger ? "var(--color-hermes-danger)" : "var(--color-hermes-border)"}`,
      }}
    >
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          cursor: "pointer",
          userSelect: "none",
          padding: "4px 0",
        }}
      >
        {open ? (
          <ChevronDown size={12} color="var(--color-hermes-text-secondary)" />
        ) : (
          <ChevronRight size={12} color="var(--color-hermes-text-secondary)" />
        )}
        {typeof icon === "string" ? <span style={{ fontSize: 12 }}>{icon}</span> : icon}
        <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, flex: 1, color: isDanger ? "var(--color-hermes-danger)" : "var(--color-hermes-text)" }}>
          {title}
        </h4>
        {!open && summary && (
          <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{summary}</span>
        )}
        {rightSlot && (
          <span onClick={(e) => e.stopPropagation()}>{rightSlot}</span>
        )}
      </div>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  )
}

// ─────────────── Workflow Action Bar ───────────────
function WorkflowActionBar({ taskId, status, qc }: { taskId: string; status: string; qc: any }) {
  const [rejectNote, setRejectNote] = useState("")
  const [showReject, setShowReject] = useState(false)
  const [ceoAnswer, setCeoAnswer] = useState("")
  const [showCeoAnswer, setShowCeoAnswer] = useState(false)
  const [editableRecs, setEditableRecs] = useState<Record<number, string>>({})

  // TRIAGE: Live-Modus (Auto-CIO), aber auch manueller Trigger moeglich
  const triageEvaluate = useMutation({
    mutationFn: () => api.wfTriageEvaluate(taskId, "CIO", true),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })
  const triageReject = useMutation({
    mutationFn: () => api.wfTriageReject(taskId, "CIO", rejectNote || "Feedback noetig"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["task", taskId] }); setShowReject(false) },
  })

  // TODO: Worker zuweisen + starten
  const assign = useMutation({
    mutationFn: (worker: string) => api.wfAssign(taskId, "CIO", worker),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })
  const start = useMutation({
    mutationFn: () => api.wfStart(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })

  // IN_PROGRESS: Submit for Review
  const submitReview = useMutation({
    mutationFn: () => api.wfSubmitReview(taskId, "system", "Worker done"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })

  // REVIEW: Tester approve / reject
  const testerApprove = useMutation({
    mutationFn: () => api.wfTesterApprove(taskId, "pi-tester", "OK"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })
  const testerReject = useMutation({
    mutationFn: () => api.wfTesterReject(taskId, "pi-tester", rejectNote || "Probleme gefunden", "Bitte fixen"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["task", taskId] }); setShowReject(false) },
  })

  // BLOCK: CIO approve / reject OR CEO antwortet auf Frage
  const cioApprove = useMutation({
    mutationFn: () => api.wfCioApprove(taskId, "CIO", "Aufgabe erledigt"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  })
  const cioReject = useMutation({
    mutationFn: () => api.wfCioReject(taskId, "CIO", rejectNote || "Nicht OK", "in_progress"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["task", taskId] }); setShowReject(false) },
  })
  const ceoAnswerMut = useMutation({
    mutationFn: (target: "todo" | "triage") => api.wfCeoAnswer(taskId, ceoAnswer || "Weiter so", target, "CEO"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["task", taskId] }); setShowCeoAnswer(false); setCeoAnswer("") },
  })
  // Recommendation anwenden (editierbar, klickbar)
  const applyRecMut = useMutation({
    mutationFn: ({ rec, kind, issueIndex }: { rec: string; kind: "title" | "description" | "general"; issueIndex: number }) =>
      api.wfApplyRecommendation(taskId, rec, kind, issueIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task", taskId] })
      qc.invalidateQueries({ queryKey: ["tasks"] })
      // Reset editable state
      setEditableRecs({})
    },
  })

  // Meta-Daten laden (CIO-Question, CEO-Answer)
  const { data: taskData } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId),
  })
  const meta = (taskData as any)?.meta || {}
  const cioQuestion = meta?.cio_question
  const ceoAnswerText = meta?.ceo_answer

  // Helper: detect kind from issue title
  function detectKind(title: string): "title" | "description" | "general" {
    const t = (title || "").toLowerCase()
    if (t.includes("titel")) return "title"
    if (t.includes("description") || t.includes("konflikt-keyword") || t.includes("priority")) return "description"
    return "general"
  }

  return (
    <div className="detail-panel-section" style={{ borderTop: "1px solid var(--color-hermes-border)", paddingTop: 14, marginTop: 14 }}>
      <h4 style={{ marginBottom: 10 }}>
        <span style={{ marginRight: 6 }}>⚡</span>
        Standard-Workflow
        <span className="badge badge-blue" style={{ marginLeft: 8, fontSize: 10 }}>{status}</span>
      </h4>

      {status === "triage" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", padding: "6px 8px", background: "var(--color-hermes-muted)", borderRadius: 4, borderLeft: "2px solid var(--color-hermes-accent-blue)" }}>
            <strong>🤖 Auto-Modus (Live):</strong> Der CIO bewertet automatisch alle 5–30s. Bei OK → GO, bei Problem → BLOCK mit Frage.
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={() => triageEvaluate.mutate()} disabled={triageEvaluate.isPending}>
              ⚡ Jetzt bewerten (manuell)
            </button>
            <button className="btn btn-sm" onClick={() => setShowReject(!showReject)}>
              ❌ Reject (Feedback)
            </button>
          </div>
          {showReject && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <textarea className="input" placeholder="Feedback fuer User..." value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} style={{ minHeight: 50 }} />
              <button className="btn btn-sm btn-danger" onClick={() => triageReject.mutate()} disabled={triageReject.isPending || !rejectNote.trim()}>
                Reject senden
              </button>
            </div>
          )}
        </div>
      )}

      {status === "todo" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            <strong>Worker zuweisen</strong> oder direkt starten:
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-sm" onClick={() => assign.mutate("pi-coder")} disabled={assign.isPending}>👨‍💻 pi-coder</button>
            <button className="btn btn-sm" onClick={() => assign.mutate("pi-tester")} disabled={assign.isPending}>🧪 pi-tester</button>
            <button className="btn btn-sm" onClick={() => assign.mutate("pi-reviewer")} disabled={assign.isPending}>🔍 pi-reviewer</button>
            <button className="btn btn-sm" onClick={() => assign.mutate("pi-fixer")} disabled={assign.isPending}>🔧 pi-fixer</button>
            <button className="btn btn-sm" onClick={() => assign.mutate("CIO")} disabled={assign.isPending}>👔 CIO</button>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => start.mutate()} disabled={start.isPending}>
            ▶ Start (GO → IN_PROGRESS)
          </button>
        </div>
      )}

      {status === "in_progress" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            <strong>Worker ist aktiv.</strong> Wenn fertig: Submit for Review.
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => submitReview.mutate()} disabled={submitReview.isPending}>
            📤 Submit for Review (IN_PROGRESS → REVIEW)
          </button>
        </div>
      )}

      {status === "review" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            <strong>Tester-Code-Review:</strong> Pruefe Schwachstellen, Bugs, schlecht programmierte Stellen.
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={() => testerApprove.mutate()} disabled={testerApprove.isPending}>
              ✅ Tester OK (→ BLOCK, Freigabe-Task erstellen)
            </button>
            <button className="btn btn-sm" onClick={() => setShowReject(!showReject)}>
              ❌ Bug gefunden (→ IN_PROGRESS)
            </button>
          </div>
          {showReject && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <textarea className="input" placeholder="Was hat der Tester gefunden?" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} style={{ minHeight: 60 }} />
              <button className="btn btn-sm btn-danger" onClick={() => testerReject.mutate()} disabled={testerReject.isPending || !rejectNote.trim()}>
                Reject (Worker muss fixen)
              </button>
            </div>
          )}
        </div>
      )}

      {status === "rueckfrage" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {cioQuestion && !ceoAnswerText && meta?.input_required !== false && (
            <div style={{ fontSize: 12, padding: "10px 12px", background: "rgba(210, 153, 34, 0.08)", border: "1px solid var(--color-hermes-accent-orange)", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--color-hermes-accent-orange)", marginBottom: 6, fontSize: 12, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span>❓</span>
                <span style={{ flex: 1 }}>CIO hat Fragen an CEOdigital/CEO ({meta.cio_question_issues?.length || 0} Issues, {meta.cio_question_questions?.length || 0} Klaerungen)</span>
                <div onClick={(e) => e.stopPropagation()}>
                  <SpeakButton
                    text={[
                      ...(meta.cio_question_issues || []).map((i: any) => `${i.title}. ${i.description || ""} Empfehlung: ${i.recommendation || ""}`),
                      ...(meta.cio_question_questions || []).map((q: any) => `${q.title}. ${q.description || ""} Empfehlung: ${q.recommendation || ""}`),
                    ].join(". ")}
                    label="Alle CIO-Fragen vorlesen"
                  />
                </div>
              </div>

              {(() => {
                const issues: any[] = meta.cio_question_issues || []
                const questions: any[] = meta.cio_question_questions || []
                const items = [
                  ...issues.map((i: any) => ({ ...i, _kind: "issue" })),
                  ...questions.map((q: any) => ({ ...q, _kind: "question" })),
                ]
                if (items.length === 0) {
                  // Fallback: alter String
                  return (
                    <div style={{ color: "var(--color-hermes-text)", fontSize: 12, whiteSpace: "pre-wrap" }}>
                      {cioQuestion}
                    </div>
                  )
                }
                return items.map((item: any, i: number) => {
                  const recKey = i
                  const currentRec = editableRecs[recKey] !== undefined ? editableRecs[recKey] : (item.recommendation || "")
                  const kind = detectKind(item.title)
                  return (
                  <div key={i} style={{ marginBottom: 10, padding: 10, background: "var(--color-hermes-surface-2)", borderRadius: 6, borderLeft: `3px solid ${item._kind === "issue" ? "var(--color-hermes-danger)" : "var(--color-hermes-accent-orange)"}` }}>
                    <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6, color: "var(--color-hermes-text)" }}>
                      {item._kind === "issue" ? "⚠️" : "❓"} {item.title}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 8, lineHeight: 1.5 }}>
                      <strong>Warum?</strong> {item.description}
                    </div>
                    {item.suggestions && item.suggestions.length > 0 && (
                      <div style={{ fontSize: 11, marginBottom: 8 }}>
                        <strong style={{ color: "var(--color-hermes-accent-blue)" }}>💡 Lösungsvorschläge:</strong>
                        <ul style={{ margin: "4px 0 0 0", paddingLeft: 20, color: "var(--color-hermes-text-secondary)", lineHeight: 1.6 }}>
                          {item.suggestions.map((s: string, j: number) => (
                            <li key={j}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {item.recommendation && (
                      <div style={{ marginTop: 6, padding: 8, background: "rgba(46, 160, 67, 0.08)", borderLeft: "2px solid var(--color-hermes-accent)", borderRadius: 4 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                          <strong style={{ color: "var(--color-hermes-accent)", fontSize: 11 }}>
                            ✅ Empfehlung (editierbar):
                          </strong>
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <span className="badge badge-green" style={{ fontSize: 9 }}>{kind === "title" ? "📝 ersetzt Titel" : kind === "description" ? "📄 ergänzt Description" : "⚙️ generisch"}</span>
                            <SpeakButton text={currentRec || item.recommendation} label="Empfehlung vorlesen" />
                          </div>
                        </div>
                        <textarea
                          className="input"
                          value={currentRec}
                          onChange={(e) => setEditableRecs({ ...editableRecs, [recKey]: e.target.value })}
                          style={{ minHeight: 70, fontSize: 11, fontFamily: "var(--font-mono)", lineHeight: 1.5, marginBottom: 6 }}
                          placeholder="Empfehlung anpassen..."
                        />
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => applyRecMut.mutate({ rec: currentRec, kind, issueIndex: i })}
                            disabled={applyRecMut.isPending || !currentRec.trim()}
                            title="Wendet die Empfehlung an und schickt den Task zurück in Triage für Re-Evaluation"
                          >
                            🚀 {applyRecMut.isPending ? "Wende an..." : "Umsetzen"}
                          </button>
                          <button
                            className="btn btn-sm"
                            onClick={() => setEditableRecs({ ...editableRecs, [recKey]: item.recommendation })}
                            disabled={currentRec === item.recommendation}
                            title="Auf Original zurücksetzen"
                          >
                            ↺ Reset
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  )
                })
              })()}

              <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                <button className="btn btn-primary btn-sm" onClick={() => setShowCeoAnswer(!showCeoAnswer)}>
                  💬 CEO antworten
                </button>
              </div>
              {showCeoAnswer && (
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                  <textarea className="input" placeholder="Deine Antwort als CEO..." value={ceoAnswer} onChange={(e) => setCeoAnswer(e.target.value)} style={{ minHeight: 60 }} />
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-sm btn-primary" onClick={() => ceoAnswerMut.mutate("todo")} disabled={ceoAnswerMut.isPending || !ceoAnswer.trim()}>
                      → Zurueck in GO
                    </button>
                    <button className="btn btn-sm" onClick={() => ceoAnswerMut.mutate("triage")} disabled={ceoAnswerMut.isPending || !ceoAnswer.trim()}>
                      → Zurueck in Triage (Re-Evaluation)
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {ceoAnswerText && (
            <div style={{ fontSize: 12, padding: "8px 12px", background: "rgba(46, 160, 67, 0.1)", border: "1px solid var(--color-hermes-accent)", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--color-hermes-accent)", marginBottom: 4, fontSize: 11 }}>
                ✅ CEO-Antwort (gesendet):
              </div>
              <div style={{ color: "var(--color-hermes-text)", fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap" }}>
                {ceoAnswerText}
              </div>
            </div>
          )}

          {!cioQuestion && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              <strong>CIO Final-Review:</strong> Aufgabe erledigt? Ziele erreicht? Code-Qualitaet OK?
            </div>
          )}

          <div style={{ display: "flex", gap: 6, marginTop: cioQuestion ? 8 : 0 }}>
            <button className="btn btn-primary btn-sm" onClick={() => cioApprove.mutate()} disabled={cioApprove.isPending}>
              ✅ CIO Approve (→ DONE)
            </button>
            <button className="btn btn-sm" onClick={() => setShowReject(!showReject)}>
              ❌ Reject (zurueck in IN_PROGRESS)
            </button>
          </div>
          {showReject && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <textarea className="input" placeholder="Grund fuer Reject..." value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} style={{ minHeight: 50 }} />
              <button className="btn btn-sm btn-danger" onClick={() => cioReject.mutate()} disabled={cioReject.isPending || !rejectNote.trim()}>
                Reject (Task in IN_PROGRESS)
              </button>
            </div>
          )}
        </div>
      )}

      {status === "done" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, color: "var(--color-hermes-accent)" }}>
          <div style={{ fontSize: 12 }}>✅ <strong>Task abgeschlossen.</strong> Vollstaendig auditiert.</div>
        </div>
      )}
    </div>
  )
}

// =====================================================================
// SopStatusSection (User-Direktive 18.06.2026)
// Zeigt aktuellen SOP-Step + Verantwortlichen + naechsten Schritt + Progress
// =====================================================================
function SopStatusSection({ taskId }: { taskId: string }) {
  const [open, setOpen] = useState(true);
  const { data, isLoading, error } = useQuery({
    queryKey: ["task-sop-status", taskId],
    queryFn: () => api.getTask(taskId),  // Fallback: getTask statt api.task.sopStatus
    refetchInterval: 10000, // alle 10s neu laden
  });

  if (isLoading) {
    return (
      <div className="detail-panel-section">
        <h4 style={{ marginBottom: 8 }}>📋 SOP-Status</h4>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>Lade SOP-Status…</div>
      </div>
    );
  }
  if (error || !data) {
    return null;
  }
  if (!data.sop_id) {
    return (
      <div className="detail-panel-section">
        <h4 style={{ marginBottom: 8 }}>📋 SOP-Status</h4>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>{data.note || "Keine SOP-Instance vorhanden."}</div>
      </div>
    );
  }

  const cur = data.current_step;
  const nxt = data.next_step;

  return (
    <div className="detail-panel-section" style={{ borderTop: "1px solid var(--color-hermes-border)", paddingTop: 12, marginTop: 12 }}>
      <h4
        onClick={() => setOpen(!open)}
        style={{ marginBottom: 8, cursor: "pointer", userSelect: "none", display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <span>📋 SOP-Status <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>({data.sop_name})</span></span>
        <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{open ? "▼" : "▶"}</span>
      </h4>

      {/* Progress Bar */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
          <span>Fortschritt: {data.completed_steps}/{data.total_steps} Schritte</span>
          <span>{data.progress_pct}%</span>
        </div>
        <div style={{ height: 6, background: "var(--color-hermes-border)", borderRadius: 3, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${data.progress_pct}%`, background: data.instance_status === "completed" ? "var(--color-hermes-accent)" : "#7c3aed", transition: "width 0.3s" }} />
        </div>
      </div>

      {open && (
        <>
          {/* Aktueller Schritt */}
          {cur ? (
            <div style={{ background: "rgba(124, 58, 237, 0.1)", border: "1px solid #7c3aed", borderRadius: 6, padding: 10, marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", marginBottom: 4 }}>Aktueller Schritt</div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>#{cur.order}: {cur.name}</div>
              <span className="badge badge-blue">👤 Verantwortlich: {cur.agent}</span>
              {cur.action && (
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 6 }}>Action: <code>{cur.action}</code></div>
              )}
            </div>
          ) : (
            <div style={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 6, padding: 10, marginBottom: 8, fontSize: 12 }}>
              {data.instance_status === "completed" ? "✅ SOP-Instance abgeschlossen" : "⏳ Kein aktiver Schritt"}
            </div>
          )}

          {/* Nächster Schritt */}
          {nxt && (
            <div style={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 6, padding: 10, marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", marginBottom: 4 }}>Nächster Schritt</div>
              <div style={{ fontSize: 12, marginBottom: 4 }}>#{nxt.order}: {nxt.name}</div>
              <span className="badge">👤 {nxt.agent}</span>
            </div>
          )}

          {/* Alle Schritte (kompakt) */}
          <details>
            <summary style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", cursor: "pointer", marginBottom: 4 }}>Alle {data.total_steps} Schritte anzeigen</summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 6 }}>
              {data.all_steps.map((s: any) => (
                <div
                  key={s.id}
                  style={{
                    fontSize: 11,
                    padding: "4px 6px",
                    borderRadius: 3,
                    background: cur && s.id === cur.id ? "rgba(124, 58, 237, 0.2)" : "transparent",
                    border: cur && s.id === cur.id ? "1px solid #7c3aed" : "1px solid transparent",
                    color: "var(--color-hermes-text)",
                    display: "flex",
                    justifyContent: "space-between",
                  }}
                >
                  <span>#{s.order}: {s.name}</span>
                  <span style={{ color: "var(--color-hermes-text-secondary)" }}>👤 {s.agent}</span>
                </div>
              ))}
            </div>
          </details>
        </>
      )}
    </div>
  );
}

