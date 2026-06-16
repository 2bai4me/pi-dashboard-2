import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { Power, Pause, CheckCircle2, ChevronDown, BookOpen, X as XIcon } from "lucide-react"
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
