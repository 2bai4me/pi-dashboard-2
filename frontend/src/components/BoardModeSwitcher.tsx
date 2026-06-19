import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { Power, Pause, CheckCircle2, ChevronDown, BookOpen, X as XIcon, Bot, Users, Server, Activity, Clock, Hash, X } from "lucide-react"
import { useState, useRef, useEffect } from "react"

// Mapping: User-Labels <-> Project.mode
export const BOARD_MODES = [
  { key: "execution", label: "live",          color: "var(--color-hermes-accent)",       icon: Power,       desc: "Standardprozess laeuft automatisch" },
  { key: "paused",    label: "Warten",        color: "var(--color-hermes-accent-orange)", icon: Pause,        desc: "Keine Bearbeitung, neue Tasks zulaessig" },
  { key: "completed", label: "Abgeschlossen", color: "var(--color-hermes-danger)",        icon: CheckCircle2, desc: "Keine neuen Tasks mehr (HTTP 409)" },
] as const

type ModeKey = typeof BOARD_MODES[number]["key"]

export function BoardModeSwitcher({ project }: { project: { id: string; mode?: string; default_sop_id?: string | null } }) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 6, marginBottom: -1 }}>
      {/* SOP-Dropdown (links neben dem Mode-Switcher) */}
      <DefaultSopDropdown project={project} />

      {/* Mode-Dropdown (live / Warten / Abgeschlossen) */}
      <ModeDropdown project={project} />

      {/* Aktive Agenten/Subagenten Badge + Dialog (Task 44c7229af57e) */}
      <ActiveAgentsBadge />
    </div>
  )
}

// ─────────────── Mode-Dropdown ───────────────
function ModeDropdown({ project }: { project: { id: string; mode?: string } }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current: typeof BOARD_MODES[number] =
    BOARD_MODES.find((m) => m.key === project.mode) || BOARD_MODES[0]
  const CurrentIcon = current.icon

  // Klick ausserhalb schliesst Dropdown
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  const setModeMut = useMutation({
    mutationFn: (mode: ModeKey) => api.setProjectMode(project.id, mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["project", project.id] })
      setOpen(false)
    },
  })

  return (
    <div ref={ref} style={{ position: "relative", marginBottom: -1 }}>
      <button
        className="mode-dropdown-trigger"
        onClick={() => setOpen(!open)}
        disabled={setModeMut.isPending}
        title={`Board-Modus: ${current.label} — ${current.desc}`}
        style={{
          color: current.color,
          fontWeight: 600,
        }}
      >
        <CurrentIcon size={11} />
        <span>{current.label}</span>
        <ChevronDown size={10} style={{ opacity: 0.7 }} />
      </button>

      {open && (
        <div className="mode-dropdown-menu">
          <div style={{ padding: "6px 10px", fontSize: 10, color: "var(--color-hermes-text-secondary)", borderBottom: "1px solid var(--color-hermes-border)" }}>
            Board-Modus waehlen
          </div>
          {BOARD_MODES.map((m) => {
            const isCurrent = m.key === current.key
            const Icon = m.icon
            return (
              <button
                key={m.key}
                className={`mode-dropdown-item ${isCurrent ? "active" : ""}`}
                onClick={() => setModeMut.mutate(m.key as ModeKey)}
                disabled={setModeMut.isPending}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon size={11} color={isCurrent ? m.color : "var(--color-hermes-text-secondary)"} />
                  <span style={{ fontWeight: isCurrent ? 600 : 400, color: isCurrent ? m.color : "var(--color-hermes-text)" }}>
                    {m.label}
                  </span>
                  {isCurrent && (
                    <span style={{ marginLeft: "auto", fontSize: 9, color: m.color }}>● aktiv</span>
                  )}
                </div>
                <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 2, paddingLeft: 17 }}>
                  {m.desc}
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─────────────── Active Agents Badge + Dialog (Task 44c7229af57e) ───────────────
function ActiveAgentsBadge() {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ["active-agents"],
    queryFn: () => api.operators.listActiveAgents(),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  })

  const total = data?.total ?? 0

  return (
    <>
      <button
        className="mode-dropdown-trigger"
        onClick={() => setOpen(true)}
        title={`${total} aktive Agenten/Subagenten. Klick fuer Details.`}
        style={{
          color: total > 0 ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)",
          fontWeight: 600,
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <Bot size={11} />
        <span>{total}</span>
      </button>

      {open && <ActiveAgentsDialog data={data} isLoading={isLoading} onClose={() => setOpen(false)} />}
    </>
  )
}

function ActiveAgentsDialog({ data, isLoading, onClose }: { data?: any; isLoading: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    function onClick(e: MouseEvent) {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener("keydown", onKey)
    document.addEventListener("mousedown", onClick)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("mousedown", onClick)
    }
  }, [onClose])

  const items: any[] = data?.items || []

  const grouped: Record<string, any[]> = {
    board_operator: [],
    sub_agent: [],
    worker_loop: [],
    in_progress_task: [],
    scheduler_job: [],
  }
  for (const item of items) {
    if (grouped[item.type]) grouped[item.type].push(item)
    else grouped[item.type] = [item]
  }

  const typeLabel: Record<string, string> = {
    board_operator: "Board-Operatoren",
    sub_agent: "Sub-Agenten (swarm-spawner)",
    worker_loop: "Worker-Loop",
    in_progress_task: "In-Progress-Tasks",
    scheduler_job: "Scheduler-Jobs",
  }

  const typeIcon: Record<string, any> = {
    board_operator: Activity,
    sub_agent: Bot,
    worker_loop: Server,
    in_progress_task: Users,
    scheduler_job: Clock,
  }

  return (
    <div
      className="modal-backdrop"
      style={{ zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
    >
      <div
        ref={dialogRef}
        className="modal"
        style={{ maxWidth: 720, width: "90vw", maxHeight: "80vh", overflow: "auto", padding: 20 }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Bot size={18} color="var(--color-hermes-accent)" />
            <h3 style={{ margin: 0, fontSize: 16 }}>Aktive Agenten & Subagenten</h3>
          </div>
          <button className="btn btn-sm" onClick={onClose} title="Schliessen">
            <X size={14} />
          </button>
        </div>

        {isLoading ? (
          <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>
            Lade Agenten-Status...
          </div>
        ) : items.length === 0 ? (
          <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>
            Keine aktiven Agenten/Subagenten.
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
              {Object.entries(data?.by_type || {}).map(([key, count]: [string, any]) => (
                <span key={key} className="badge badge-gray" style={{ fontSize: 11 }}>
                  {typeLabel[key] || key}: {count}
                </span>
              ))}
            </div>

            {Object.entries(grouped).map(([type, groupItems]) => {
              if (groupItems.length === 0) return null
              const Icon = typeIcon[type] || Bot
              return (
                <div key={type} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, fontWeight: 600, fontSize: 13 }}>
                    <Icon size={14} color="var(--color-hermes-accent-blue)" />
                    {typeLabel[type] || type}
                    <span className="badge badge-blue" style={{ fontSize: 10 }}>{groupItems.length}</span>
                  </div>
                  <table className="data-table" style={{ fontSize: 11 }}>
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th>Session-ID</th>
                        <th>Task-ID</th>
                        <th>Status / Info</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupItems.map((item: any, idx: number) => (
                        <tr key={idx}>
                          <td>
                            <div style={{ fontWeight: 500 }}>{item.agent}</div>
                            {item.role && item.role !== item.agent && (
                              <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>{item.role}</div>
                            )}
                          </td>
                          <td className="mono" style={{ fontSize: 10, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
                            {item.session_id || "—"}
                          </td>
                          <td className="mono" style={{ fontSize: 10 }}>
                            {item.task_id ? item.task_id.slice(0, 12) : "—"}
                          </td>
                          <td style={{ fontSize: 10 }}>
                            <span className={`badge badge-${item.status === "running" ? "green" : "orange"}`} style={{ fontSize: 9 }}>
                              {item.status}
                            </span>
                            {item.uptime_s !== undefined && (
                              <div style={{ color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                                {Math.floor(item.uptime_s / 60)}m {item.uptime_s % 60}s
                              </div>
                            )}
                            {item.last_heartbeat_age_s !== undefined && (
                              <div style={{ color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                                Heartbeat: {item.last_heartbeat_age_s}s
                              </div>
                            )}
                            {item.title && (
                              <div style={{ color: "var(--color-hermes-text-secondary)", marginTop: 2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                                {item.title}
                              </div>
                            )}
                            {item.pid && (
                              <div style={{ color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                                PID: {item.pid}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            })}

            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textAlign: "right", marginTop: 8 }}>
              Letzte Aktualisierung: {data?.checked_at ? new Date(data.checked_at).toLocaleString("de-DE") : "—"}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────── Default-SOP-Dropdown ───────────────
function DefaultSopDropdown({ project }: { project: { id: string; default_sop_id?: string | null } }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // SOPs laden
  const { data: sopsData, isLoading } = useQuery({
    queryKey: ["sops"],
    queryFn: () => api.listSops(),
  })
  const sops: any[] = (sopsData as any)?.items || []
  const currentSop = sops.find((s: any) => s.id === project.default_sop_id)
  const currentLabel = currentSop ? currentSop.name : "Standard-SOP waehlen…"

  // Klick ausserhalb schliesst Dropdown
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  // SOP setzen
  const setSopMut = useMutation({
    mutationFn: (sopId: string | null) => api.setProjectDefaultSop(project.id, sopId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["project", project.id] })
      setOpen(false)
    },
  })

  return (
    <div ref={ref} style={{ position: "relative", marginBottom: -1 }}>
      <button
        className="sop-dropdown-trigger"
        onClick={() => setOpen(!open)}
        disabled={isLoading}
        title="Standard-SOP fuer den Prozessdurchlauf"
        style={currentSop ? { color: "var(--color-hermes-text)" } : { color: "var(--color-hermes-text-secondary)" }}
      >
        <BookOpen size={11} />
        <span style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {isLoading ? "Lade SOPs…" : currentLabel}
        </span>
        <ChevronDown size={10} style={{ opacity: 0.6 }} />
      </button>

      {open && (
        <div className="sop-dropdown-menu">
          <div style={{ padding: "6px 10px", fontSize: 10, color: "var(--color-hermes-text-secondary)", borderBottom: "1px solid var(--color-hermes-border)" }}>
            Standard-SOP auswaehlen
          </div>
          {sops.length === 0 ? (
            <div style={{ padding: "10px 12px", fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              Keine SOPs vorhanden. Lege eine im <strong>SOP-Tab</strong> an.
            </div>
          ) : (
            sops.map((s: any) => {
              const isCurrent = s.id === project.default_sop_id
              return (
                <button
                  key={s.id}
                  className={`sop-dropdown-item ${isCurrent ? "active" : ""}`}
                  onClick={() => setSopMut.mutate(s.id)}
                  disabled={setSopMut.isPending}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <BookOpen size={11} color={isCurrent ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)"} />
                    <span style={{ fontWeight: isCurrent ? 600 : 400 }}>{s.name}</span>
                    {isCurrent && <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--color-hermes-accent)" }}>● aktiv</span>}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 2, paddingLeft: 17 }}>
                    {s.category} · v{s.version} · {s.step_count} Steps
                  </div>
                </button>
              )
            })
          )}
          {project.default_sop_id && (
            <button
              className="sop-dropdown-item"
              onClick={() => setSopMut.mutate(null)}
              disabled={setSopMut.isPending}
              style={{ color: "var(--color-hermes-danger)", borderTop: "1px solid var(--color-hermes-border)" }}
            >
              <XIcon size={10} /> Auswahl aufheben
            </button>
          )}
        </div>
      )}
    </div>
  )
}
