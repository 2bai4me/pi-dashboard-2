import { useState, useEffect, useMemo, useRef } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import {
  Plus, Search, ChevronDown, ChevronRight, CheckCircle2, ListChecks,
  Filter, BarChart3, ClipboardList, ListTodo, AlertCircle, FolderKanban,
  X, Flame, Hash, RotateCcw, Sparkles, ChevronLeft, ChevronRight as ChevronRightIcon,
  Trash2, Users, Brain, MessageSquare, HelpCircle, Send, Loader2,
} from "lucide-react"
import BrainstormTab from "../components/BrainstormTab"
import KpisTab from "../components/KpisTab"
import BrainDevTab from "../components/BrainDevTab"
import { SpeakButton } from "../components/SpeakButton"
import { BoardModeSwitcher } from "../components/BoardModeSwitcher"
import { NewTaskModal } from "../components/NewTaskModal"
import { CioTriageSection } from "../components/CioTriageSection"
import { TaskDetailPanel } from "../components/TaskDetailPanel"
import { UserInputForm } from "../components/UserInputForm"

type ProjectTab = "brainstorm" | "requirements" | "tasks" | "board" | "kpis" | "braindev"

const COLUMNS = [
  { key: "triage",       label: "Triage" },
  { key: "go",           label: "GO" },
  { key: "in_progress",  label: "In Progress" },
  { key: "review",       label: "Review" },
  { key: "rueckfrage",   label: "Rückfrage" },
  { key: "warten",       label: "Warten" },
  { key: "done",         label: "Done" },
] as const

// Farben je Status (linker Akzent-Border der Spalten-Karten)
const STATUS_COLORS: Record<string, string> = {
  triage: "var(--color-hermes-text-secondary)",
  go: "var(--color-hermes-accent-blue)",
  in_progress: "var(--color-hermes-accent-orange)",
  review: "#a371f7", // lila
  rueckfrage: "var(--color-hermes-danger)", // rot
  warten: "#58a6ff", // cyan/blau-grau
  done: "var(--color-hermes-accent)",
}

type ColKey = typeof COLUMNS[number]["key"]

export default function Kanban() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const projectIdFromUrl = searchParams.get("projectId")
  const { data: projectsData, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
    // User-Direktive 17.06.2026 (Prio 100 BUG-Fix): Cache-Invalidation
    // staleTime: 0 erzwingt sofortigen Refetch nach invalidateQueries
    // refetchOnMount: "always" laedt bei jedem Mount frische Daten
    staleTime: 0,
    refetchOnMount: "always",
  })
  const projects: any[] = (projectsData as any)?.items || []
  const [showNewProject, setShowNewProject] = useState(false)

  // Aktives Projekt aus URL ableiten
  const activeProject = projectIdFromUrl
    ? projects.find((p: any) => p.id === projectIdFromUrl) || null
    : null
  // Optional: Detail-Task aus URL
  const detailTaskId = searchParams.get("task")

  function openProject(id: string, tab: ProjectTab = "board") {
    setSearchParams({ projectId: id, tab })
  }

  function backToList() {
    setSearchParams({})
  }

  if (isLoading) {
    return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Lade Projekte…</div>
  }

  // Kein Projekt in URL -> Projekt-Liste zeigen
  if (!activeProject) {
    return (
      <div>
        <ProjectList
          projects={projects}
          onSelect={(id) => openProject(id, "board")}
          onNew={() => setShowNewProject(true)}
        />
        {showNewProject && (
          <NewProjectModal
            onClose={() => setShowNewProject(false)}
            onCreated={(p: any) => {
              setShowNewProject(false)
              // User-Direktive 17.06.2026 (Prio 100 BUG-Fix): refetchType: "all"
              // erzwingt SOFORTIGEN Refetch — kein Warten auf staleTime
              qc.invalidateQueries({ queryKey: ["projects"], refetchType: "all" })
              openProject(p.id, "board")
            }}
          />
        )}
      </div>
    )
  }

  // Projekt in URL -> Workspace zeigen
  return (
    <div>
      <ProjectWorkspace
        project={activeProject}
        onBack={backToList}
        onNewProject={() => setShowNewProject(true)}
        initialTaskId={detailTaskId}
      />
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={(p: any) => {
            // User-Direktive 17.06.2026 (Prio 100 BUG-Fix): refetchType: "all"
            // erzwingt SOFORTIGEN Refetch — kein Warten auf staleTime
            qc.invalidateQueries({ queryKey: ["projects"], refetchType: "all" })
            setShowNewProject(false)
            openProject(p.id, "board")
          }}
        />
      )}
    </div>
  )
}

// ─────────────── Project List (Kachel-View) ───────────────
function ProjectList({ projects, onSelect, onNew }: { projects: any[]; onSelect: (id: string) => void; onNew: () => void }) {
  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <FolderKanban size={20} color="var(--color-hermes-accent-blue)" />
          <h1>Projekte</h1>
        </div>
        <p>Projekt-Management mit Brainstorming, Anforderungen, Tasks & Board</p>
      </div>

      <button className="btn btn-primary mb-3" onClick={onNew}>
        <Plus size={14} /> New Project
      </button>

      {projects.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          Noch keine Projekte. Klicke <strong>+ New Project</strong> um zu starten.
        </div>
      ) : (
        <div className="card-grid">
          {projects.map((p: any) => (
            <div
              key={p.id}
              className="project-card"
              onClick={() => onSelect(p.id)}
              style={{ borderLeftColor: p.mode === "execution" ? "var(--color-hermes-accent)" : p.mode === "completed" ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text-secondary)" }}
            >
              <div className="project-card-name">{p.name}</div>
              <div className="project-card-desc">{p.description || "(keine Beschreibung)"}</div>
              <div className="project-card-meta">
                <span className="badge badge-gray">{p.category}</span>
                <span>· {p.task_count || 0} Tasks</span>
                <span>· ${(p.total_cost_usd || 0).toFixed(4)}</span>
              </div>
              <div className="project-card-meta" style={{ marginTop: 6, fontSize: 10 }}>
                Created: {new Date(p.created_at).toLocaleDateString("de-DE")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────── Project Workspace (Detail mit Tabs) ───────────────
function ProjectWorkspace({ project, onBack, onNewProject, initialTaskId }: { project: any; onBack: () => void; onNewProject: () => void; initialTaskId?: string | null }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTab = (searchParams.get("tab") as ProjectTab) || "board"
  const [tab, setTab] = useState<ProjectTab>(initialTab)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(initialTaskId || null)
  // User-Direktive 17.06.2026: User-Input-Modal (oeffnet bei Klick auf Input-Symbol der Task-Kachel)
  const [userInputTaskId, setUserInputTaskId] = useState<string | null>(null)
  const qc = useQueryClient()

  function setTabAndUrl(t: ProjectTab) {
    setTab(t)
    setSearchParams({ projectId: project.id, tab: t })
  }

  // Auf Custom-Event vom Brainstorm-Tab hoeren (Generate Requirements)
  useEffect(() => {
    const h = (e: any) => setTabAndUrl(e.detail)
    window.addEventListener("kanban-tab-change", h)
    return () => window.removeEventListener("kanban-tab-change", h)
  }, [project.id])

  // === SSE Live-Updates (User-Direktive 18.06.2026) ===
  // Server-Sent Events vom Backend (GET /api/kanban/events/{project_id})
  // Push-Benachrichtigung bei task_created / task_status_changed / etc.
  // Reconnect-Logic bei Disconnect (2s Backoff).
  // Polling (refetchInterval) bleibt als Fallback erhalten.
  const sseRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const [sseStatus, setSseStatus] = useState<"connecting" | "connected" | "disconnected">("connecting")

  useEffect(() => {
    if (!project.id) return
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      setSseStatus("connecting")
      const es = new EventSource(`/api/kanban/events/${encodeURIComponent(project.id)}`)
      sseRef.current = es

      es.addEventListener("connected", () => {
        if (cancelled) return
        setSseStatus("connected")
        // Bei (Re-)Connect: sofortiger Refetch, damit initialer Stand frisch ist
        qc.invalidateQueries({ queryKey: ["tasks", project.id] })
        qc.invalidateQueries({ queryKey: ["projects"] })
      })

      // Server-Events, die Query-Invalidation triggern (siehe backend/app/events.py)
      const handleMutation = (eventName: string) => (ev: MessageEvent) => {
        if (cancelled) return
        try {
          const data = JSON.parse(ev.data)
          console.log(`[sse:${eventName}]`, data)
        } catch { /* ignore */ }
        qc.invalidateQueries({ queryKey: ["tasks", project.id] })
        qc.invalidateQueries({ queryKey: ["projects"] })
      }
      es.addEventListener("task_created", handleMutation("task_created"))
      es.addEventListener("task_status_changed", handleMutation("task_status_changed"))
      es.addEventListener("task_priority_changed", handleMutation("task_priority_changed"))
      es.addEventListener("task_usage_reported", handleMutation("task_usage_reported"))
      es.addEventListener("project_mode_changed", handleMutation("project_mode_changed"))
      es.addEventListener("agent_question_created", handleMutation("agent_question_created"))
      es.addEventListener("agent_question_answered", handleMutation("agent_question_answered"))

      es.onerror = () => {
        if (cancelled) return
        setSseStatus("disconnected")
        es.close()
        sseRef.current = null
        // Auto-Reconnect nach 2s
        if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = window.setTimeout(connect, 2000)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (sseRef.current) {
        sseRef.current.close()
        sseRef.current = null
      }
    }
  }, [project.id, qc])

  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <ListChecks size={20} color="var(--color-hermes-accent-blue)" />
          <h1>Projekte</h1>
          <span className="workspace-breadcrumb">/ {project.name}</span>
          {/* Live-Indikator (User-Direktive 17.06.2026: minimalistisch) - nur ein Punkt, kein blinkender Text */}
          <span
            className={`live-indicator live-indicator-${sseStatus}`}
            title={
              sseStatus === "connected" ? "Echtzeit-Updates aktiv (SSE)" :
              sseStatus === "connecting" ? "Verbinde zu Live-Stream..." :
              "Live-Stream unterbrochen — reconnect in 2s"
            }
            style={{ marginLeft: 12, display: "inline-flex", alignItems: "center", gap: 4, cursor: "help" }}
          >
            <span
              className="status-dot"
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background:
                  sseStatus === "connected" ? "var(--color-hermes-accent)" :
                  sseStatus === "connecting" ? "var(--color-hermes-accent-orange)" :
                  "var(--color-hermes-danger)",
                boxShadow:
                  sseStatus === "connected" ? "0 0 6px var(--color-hermes-accent)" :
                  sseStatus === "connecting" ? "0 0 6px var(--color-hermes-accent-orange)" :
                  "0 0 6px var(--color-hermes-danger)",
                animation: sseStatus === "connected" ? "pulse-live 1.8s ease-in-out infinite" : "none",
              }}
            />
          </span>
        </div>
        <p>Projekt-Management mit Brainstorming, Anforderungen, Tasks & Board</p>
      </div>

      <div className="subtab-bar">
        <button className={`subtab ${tab === "brainstorm" ? "active" : ""}`} onClick={() => setTabAndUrl("brainstorm")}>
          <Sparkles size={14} /> Brainstorm
        </button>
        <button className={`subtab ${tab === "requirements" ? "active" : ""}`} onClick={() => setTabAndUrl("requirements")}>
          <ClipboardList size={14} /> Requirements
        </button>
        <button className={`subtab ${tab === "tasks" ? "active" : ""}`} onClick={() => setTabAndUrl("tasks")}>
          <ListTodo size={14} /> Tasks
        </button>
        <button className={`subtab ${tab === "board" ? "active" : ""}`} onClick={() => setTabAndUrl("board")}>
          <ListChecks size={14} /> Board
        </button>
        <button className={`subtab ${tab === "kpis" ? "active" : ""}`} onClick={() => setTabAndUrl("kpis")}>
          <BarChart3 size={14} /> KPIs
        </button>
        <button className={`subtab ${tab === "braindev" ? "active" : ""}`} onClick={() => setTabAndUrl("braindev")}>
          <Brain size={14} /> Brain DEV
        </button>

        <div style={{ flex: 1 }} />

        <span className="badge badge-blue" style={{ fontSize: 10 }}>{project.name}</span>
        <BoardModeSwitcher project={project} />
      </div>

      {tab === "board" && (
        <BoardView
          projectId={project.id}
          onSelectTask={setSelectedTaskId}
          onUserInputClick={(taskId) => setUserInputTaskId(taskId)}
        />
      )}
      {tab === "tasks" && (
        <TasksView
          projectId={project.id}
          onSelectTask={setSelectedTaskId}
          onUserInputClick={(taskId) => setUserInputTaskId(taskId)}
        />
      )}
      {tab === "brainstorm" && (
        <BrainstormTab projectId={project.id} project={project} />
      )}
      {tab === "requirements" && (
        <RequirementsTabPlaceholder projectId={project.id} projectName={project.name} />
      )}
      {tab === "kpis" && (
        <KpisTab projectId={project.id} />
      )}
      {tab === "braindev" && (
        <BrainDevTab />
      )}

      {selectedTaskId && (
        <TaskDetailPanel
          taskId={selectedTaskId}
          projectName={project.name}
          onClose={() => setSelectedTaskId(null)}
        />
      )}

      {/* User-Input-Modal (User-Direktive 17.06.2026) */}
      {userInputTaskId && (
        <UserInputModal
          taskId={userInputTaskId}
          onClose={() => setUserInputTaskId(null)}
          onAnswered={() => {
            setUserInputTaskId(null)
            qc.invalidateQueries({ queryKey: ["tasks", project.id] })
            qc.invalidateQueries({ queryKey: ["agent-questions"] })
            qc.invalidateQueries({ queryKey: ["agent-questions-pending"] })
          }}
        />
      )}
    </div>
  )
}

// ─────────────── Board View (5-Spalten) ───────────────
function BoardView({ projectId, onSelectTask, onUserInputClick }: {
  projectId: string
  onSelectTask: (id: string) => void
  onUserInputClick: (id: string) => void
}) {
  const qc = useQueryClient()
  const [showNewTask, setShowNewTask] = useState(false)
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId, limit: 500 }),
    refetchInterval: 3000, // Fallback-Polling alle 3s (SSE ist primärer Realtime-Channel)
    refetchOnWindowFocus: true,
  })
  const tasks: any[] = (tasksData as any)?.items || []
  const triageCount = tasks.filter((t: any) => t.status === "triage").length
  const [activeOnly, setActiveOnly] = useState(false)

  // === Drag&Drop: Task in andere Spalte schieben (User-Direktive 17.06.2026) ===
  // Bei status=triage wird im Backend automatisch die default_sop_id neu gestartet
  const dropMut = useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: string }) =>
      (api as any).setTaskStatus(taskId, { status: newStatus }),
    onSuccess: (resp: any, vars: any) => {
      // Cache invalidieren
      qc.invalidateQueries({ queryKey: ["tasks", projectId] })
      qc.invalidateQueries({ queryKey: ["agent-questions"] })
      // Bei SOP-Neustart: Hinweis im Console
      if (resp?.sop_instance_id) {
        console.log(`[Drag&Drop] SOP neu gestartet fuer Task ${vars.taskId.slice(0, 12)}: ${resp.sop_instance_id}`)
      }
    },
  })
  function handleTaskDrop(taskId: string, newStatus: string) {
    // Validierung: gleiche Spalte = kein API-Call
    const t = tasks.find((x: any) => x.id === taskId)
    if (!t || t.status === newStatus) return
    dropMut.mutate({ taskId, newStatus })
  }

  // === Fallback: Task per Button in der Sidebar in andere Spalte verschieben (User-Direktive 17.06.2026) ===
  // Drag&Drop ist nicht in allen Browsern zuverlaessig; diese Funktion ermoeglicht das Verschieben
  // ohne Drag&Drop (z.B. ueber die Sidebar mit dem neuen "Verschieben"-Button).
  const moveTask = (taskId: string, newStatus: string) => {
    if (!taskId || !newStatus) return
    dropMut.mutate({ taskId, newStatus })
  }

  // Refs + State fuer horizontales Scrollen
  const boardRef = useRef<HTMLDivElement | null>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  // Selektion-Filter: zeigt nur den ausgewaehlten Task + dessen Sub-Tasks
  const [selectionActive, setSelectionActive] = useState(false)

  function updateScrollState() {
    const el = boardRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
  }

  useEffect(() => {
    updateScrollState()
    const el = boardRef.current
    if (!el) return
    el.addEventListener("scroll", updateScrollState)
    const ro = new ResizeObserver(updateScrollState)
    ro.observe(el)
    return () => {
      el.removeEventListener("scroll", updateScrollState)
      ro.disconnect()
    }
  }, [])

  // Re-Pruefen wenn Spalten/Tasks sich aendern (wird nach visibleColumns weiter unten registriert)
  function scrollBy(dx: number) {
    boardRef.current?.scrollBy({ left: dx, behavior: "smooth" })
  }

  function scrollToStart() {
    boardRef.current?.scrollTo({ left: 0, behavior: "smooth" })
  }

  function scrollToEnd() {
    const el = boardRef.current
    if (!el) return
    el.scrollTo({ left: el.scrollWidth, behavior: "smooth" })
  }

  const tasksByStatus = useMemo(() => {
    // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    // DB-Status "todo" entspricht der Anzeige-Spalte "GO" (siehe status_labels.py).
    // Wir mappen daher den DB-Key "todo" auf die Spalte "go".
    const m: Record<string, any[]> = {
      triage: [], go: [], in_progress: [], review: [],
      rueckfrage: [], warten: [], done: [],
    }
    for (const t of tasks) {
      // Normalisierung: DB-Key -> Spalten-Key
      let colKey = t.status
      if (t.status === "todo") colKey = "go"
      if (m[colKey]) m[colKey].push(t)
      // Fallback: alte 'block'-Tasks werden als 'rueckfrage' angezeigt
      else if (t.status === "block") m.rueckfrage.push(t)
    }
    return m
  }, [tasks])

  // Spalten-Filter: "Alle" = alle Spalten; "Aktiv" = nur Spalten mit Tasks (Done immer ausgeblendet)
  const visibleColumns = useMemo(() => {
    if (!activeOnly) return COLUMNS
    return COLUMNS.filter((col) => {
      if (col.key === "done") return false // Done-Spalte im Aktiv-Modus immer ausblenden
      return tasksByStatus[col.key].length > 0
    })
  }, [activeOnly, tasksByStatus])

  // Re-Pruefen der Scroll-Buttons wenn Spalten/Tasks sich aendern
  useEffect(() => {
    const t = setTimeout(updateScrollState, 50)
    return () => clearTimeout(t)
  }, [visibleColumns.length, activeOnly, tasks.length])

  // Search-/Filter-State (in der New-Task-Zeile)
  const [searchText, setSearchText] = useState("")
  const [prioOrder, setPrioOrder] = useState<"desc" | "asc" | "newest" | "oldest">("desc")
  const [showFilter, setShowFilter] = useState(false)

  // Sortier-/Filter-Logik: wendet search + prioOrder auf tasksByStatus an
  const visibleTasksByStatus = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    const matches = (t: any) =>
      !q ||
      // === User-Direktive 17.06.2026 (Prio 100 BUG-Fix): ID-Suche hinzugefuegt ===
      (t.id || "").toLowerCase().includes(q) ||
      (t.title || "").toLowerCase().includes(q) ||
      (t.description || "").toLowerCase().includes(q) ||
      (t.assigned_role || "").toLowerCase().includes(q) ||
      (Array.isArray(t.tags) && t.tags.some((tg: string) => tg.toLowerCase().includes(q))) ||
      // Success-Criteria durchsuchen
      (Array.isArray(t.success_criteria) && t.success_criteria.some((sc: any) =>
        (typeof sc === "string" ? sc : sc?.text || "").toLowerCase().includes(q)
      ))
    const sortFns: Record<string, (a: any, b: any) => number> = {
      desc:    (a, b) => (b.priority || 0) - (a.priority || 0),
      asc:     (a, b) => (a.priority || 0) - (b.priority || 0),
      newest:  (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime(),
      oldest:  (a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime(),
    }
    const out: Record<string, any[]> = {}
    for (const k of Object.keys(tasksByStatus)) {
      out[k] = [...tasksByStatus[k]].filter(matches).sort(sortFns[prioOrder] || sortFns.desc)
    }
    return out
  }, [tasksByStatus, searchText, prioOrder])

  return (
    <div>
      <div className="triage-bar">
        {/* Spalten-Navigation: < ALLE > (nur Board-Tab) */}
        <div className="board-scrollbar" style={{ marginTop: 0, padding: "4px 6px" }}>
          <button
            className="btn btn-sm"
            onClick={scrollToStart}
            disabled={!canScrollLeft}
            title="An den Anfang springen"
            aria-label="An den Anfang"
          >
            «
          </button>
          <button
            className="btn btn-sm"
            onClick={() => scrollBy(-320)}
            disabled={!canScrollLeft}
            title="Links scrollen"
            aria-label="Links scrollen"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            className={`btn btn-sm ${activeOnly ? "btn-primary" : ""}`}
            onClick={() => setActiveOnly(!activeOnly)}
            title="Zwischen allen Spalten und nur aktiven Spalten umschalten"
          >
            {activeOnly ? "Aktiv" : "Alle"}
          </button>
          <button
            className="btn btn-sm"
            onClick={() => scrollBy(320)}
            disabled={!canScrollRight}
            title="Rechts scrollen"
            aria-label="Rechts scrollen"
          >
            <ChevronRightIcon size={14} />
          </button>
          <button
            className="btn btn-sm"
            onClick={scrollToEnd}
            disabled={!canScrollRight}
            title="Ans Ende springen"
            aria-label="Ans Ende"
          >
            »
          </button>
        </div>

        {/* BUGFIX: 'New Task'-Button war kaputt (nur alert). Jetzt echtes Modal. */}
        <button
          className="btn btn-sm btn-primary"
          onClick={() => setShowNewTask(true)}
          title="Neuen Task anlegen"
        >
          <Plus size={12} /> New Task
        </button>

        <div className="triage-bar-right">
          <div style={{ position: "relative" }}>
            <Search size={12} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--color-hermes-text-secondary)" }} />
            <input
              className="input"
              placeholder="Volltextsuche..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ paddingLeft: 26, width: 200, fontSize: 12 }}
            />
          </div>
          <select
            className="select"
            style={{ fontSize: 12 }}
            value={prioOrder}
            onChange={(e) => setPrioOrder(e.target.value as any)}
            title="Sortierung"
          >
            <option value="desc">↓ Prio</option>
            <option value="asc">↑ Prio</option>
            <option value="newest">Neueste</option>
            <option value="oldest">Älteste</option>
          </select>
          <button
            className={`btn btn-sm ${showFilter ? "btn-primary" : ""}`}
            onClick={() => setShowFilter(!showFilter)}
            title="Filter"
          >
            <Filter size={12} /> Filter
          </button>
        </div>
      </div>

      <div className="board" ref={boardRef}>
        {visibleColumns.length === 0 ? (
          <div className="card" style={{ gridColumn: "1 / -1", textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
            Keine aktiven Spalten. Wechsle auf <strong>Alle</strong>, um alle Status zu sehen.
          </div>
        ) : (
          visibleColumns.map((col) => {
            const colTasks = visibleTasksByStatus[col.key]
            return (
              <div key={col.key} className="board-column">
                <div className={`board-column-header ${col.key}`}>
                  <span>{col.label}</span>
                  <span className="board-column-count">{colTasks.length}</span>
                </div>
                <div
                  className="board-column-body"
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.dataTransfer.dropEffect = "move"
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    const taskId = e.dataTransfer.getData("application/task-id") || e.dataTransfer.getData("text/plain")
                    if (taskId && col.key) {
                      handleTaskDrop(taskId, col.key)
                    }
                  }}
                  style={{ minHeight: 60 }}
                >
                  {colTasks.length === 0 ? (
                    <div className="board-column-empty">Empty</div>
                  ) : (
                    colTasks.map((t: any) => (
                      <TaskCard
                        key={t.id}
                        task={t}
                        onClick={() => onSelectTask(t.id)}
                        onUserInputClick={() => onUserInputClick(t.id)}
                      />
                    ))
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* NewTask-Modal mit KI-Validation (User-Direktive 17.06.2026) */}
      {showNewTask && (
        <NewTaskModal
          projectId={projectId}
          onClose={() => setShowNewTask(false)}
          onCreated={() => {
            setShowNewTask(false)
            qc.invalidateQueries({ queryKey: ["tasks", projectId] })
          }}
        />
      )}
    </div>
  )
}

// ─────────────── Task Card (Board) ───────────────
function TaskWaitingBadge({ taskId }: { taskId: string }) {
  // Prueft, ob fuer diesen Task gerade eine offene Transition laeuft
  // (transition_at gesetzt, processing_at = +5s, completed_at = null).
  // Wenn ja: zeige animierten "wartet 5s"-Badge mit Countdown.
  const { data } = useQuery({
    queryKey: ["task-waiting", taskId],
    queryFn: () => api.listTransitions({ task_id: taskId, limit: 5 }),
    refetchInterval: 1000, // alle 1s aktualisieren fuer Countdown
  })
  const transitions: any[] = (data as any)?.items || []
  const pending = transitions.find((t: any) => t.completed_at == null && t.delay_s > 0)
  const [remaining, setRemaining] = useState<number>(0)

  useEffect(() => {
    if (!pending) {
      setRemaining(0)
      return
    }
    const update = () => {
      const processingAt = new Date(pending.processing_at).getTime()
      const now = Date.now()
      const left = Math.max(0, processingAt - now)
      setRemaining(Math.ceil(left / 1000))
    }
    update()
    const id = setInterval(update, 250)
    return () => clearInterval(id)
  }, [pending?.id, pending?.processing_at])

  if (!pending) return null
  // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
  // Display-Namen vom Backend verwenden, damit der User "GO → In Progress"
  // sieht statt "todo → in_progress".
  const from = pending.from_status_display || pending.from_status || "—"
  const to = pending.to_status_display || pending.to_status || "—"
  return (
    <div
      style={{
        background: "linear-gradient(90deg, var(--color-hermes-accent-blue), var(--color-hermes-accent))",
        color: "#fff",
        fontSize: 10,
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: 3,
        marginBottom: 6,
        display: "flex",
        alignItems: "center",
        gap: 6,
        animation: "pulse-wait 1s ease-in-out infinite",
      }}
      title={`Warte-Periode: ${from} -> ${to} (transition_started). Auto-Claim / Verarbeitung in ${remaining}s`}
    >
      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, background: "#fff", animation: "blink 0.5s ease-in-out infinite" }} />
      <span>⏱ wartet {remaining}s</span>
      <span style={{ opacity: 0.85, fontWeight: 400 }}>
        ({from} → {to})
      </span>
    </div>
  )
}

function TaskCard({ task, onClick, onUserInputClick }: {
  task: any
  onClick: () => void
  onUserInputClick?: () => void
}) {
  const [copied, setCopied] = useState(false)

  function copyId(e: React.MouseEvent) {
    e.stopPropagation()
    navigator.clipboard.writeText(task.id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  // Optische Hervorhebung fuer offene Tasks (User-Direktive 16.06.2026)
  const hasOpenCioQuestion = !!(task.meta && (task.meta as any).cio_question)
  const isOpen = ["triage", "rueckfrage", "warten"].includes(task.status) && (hasOpenCioQuestion || !task.success_criteria || task.success_criteria.length === 0)
  const openIssuesCount = (task.meta && (task.meta as any).cio_question_issues?.length) || 0
  const openQuestionsCount = (task.meta && (task.meta as any).cio_question_questions?.length) || 0

  return (
    <div
      className={`task-card ${task.status === "done" ? "task-card-done" : ""} ${isOpen ? "task-card-open" : ""}`}
      onClick={onClick}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", task.id)
        e.dataTransfer.setData("application/task-id", task.id)
        e.dataTransfer.effectAllowed = "move"
      }}
      style={{ cursor: "grab", ...(isOpen ? { borderLeft: "3px solid var(--color-hermes-accent-orange)" } : {}) }}
    >
      {/* Warte-Badge: zeigt 5s-Delay visuell an, wenn Task gerade transitiert */}
      <TaskWaitingBadge taskId={task.id} />
      {/* OFFEN-Badge fuer Tasks mit CIO-Fragen oder fehlenden Erfolgskriterien (User-Direktive 16.06.2026) */}
      {isOpen && (
        <div style={{
          fontSize: 9, padding: "1px 5px", marginBottom: 4,
          background: "var(--color-hermes-accent-orange)", color: "#000",
          borderRadius: 3, display: "inline-flex", alignItems: "center", gap: 3,
          fontWeight: 600,
        }} title={`${openIssuesCount} Issues, ${openQuestionsCount} Klaerungen offen`}>
          ⚠ OFFEN
          {(openIssuesCount + openQuestionsCount) > 0 && (
            <span style={{ background: "#000", color: "var(--color-hermes-accent-orange)", padding: "0 3px", borderRadius: 8, fontSize: 8 }}>
              {openIssuesCount + openQuestionsCount}
            </span>
          )}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span className={`id-badge id-badge-board ${copied ? "id-badge-copied" : ""}`} onClick={copyId} title={`Vollstaendige ID: ${task.id} (Klick zum Kopieren)`}>
          {task.id.slice(0, 12)}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
          <Flame size={11} color={task.priority >= 80 ? "var(--color-hermes-danger)" : task.priority >= 50 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-text-secondary)"} />
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{task.priority}</span>
        </div>
      </div>
      <div className="title">{task.title}</div>
      {/* User-Input-Symbol (User-Direktive 17.06.2026): rueckfrage ODER input_required */}
      {(task.status === "rueckfrage" || task.meta?.input_required) && (
        <button
          onClick={(e) => { e.stopPropagation(); onUserInputClick?.() }}
          title="User-Input erforderlich — klicken zum Beantworten"
          style={{
            background: task.status === "rueckfrage" ? "rgba(220, 38, 38, 0.15)" : "rgba(245, 158, 11, 0.15)",
            border: `1px solid ${task.status === "rueckfrage" ? "#dc2626" : "#f59e0b"}`,
            color: task.status === "rueckfrage" ? "#dc2626" : "#f59e0b",
            borderRadius: 4, padding: "4px 8px", fontSize: 11,
            cursor: "pointer", display: "flex", alignItems: "center",
            gap: 4, marginTop: 6, width: "100%", justifyContent: "center",
          }}
        >
          <MessageSquare size={11} />
          <span style={{ fontWeight: 600 }}>
            {task.status === "rueckfrage" ? "Rueckfrage" : "Input erforderlich"}
          </span>
        </button>
      )}
      <div className="meta">
        {task.assigned_role && <span className="badge badge-blue">💻 {task.assigned_role}</span>}
        {task.level && <span className="badge badge-gray">Level {task.level}</span>}
        {Array.isArray(task.success_criteria) && task.success_criteria.length > 0 && (
          <span className="badge badge-green" style={{ fontSize: 10 }}>
            <CheckCircle2 size={9} /> {task.success_criteria.length} SC
          </span>
        )}
      </div>
      {task.success_criteria && (Array.isArray(task.success_criteria) ? task.success_criteria.length : 0) > 0 && (
        <div style={{ marginTop: 6, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
          {(Array.isArray(task.success_criteria) ? task.success_criteria : []).slice(0, 2).map((sc: any, i: number) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <CheckCircle2 size={9} color="var(--color-hermes-accent)" />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{typeof sc === "string" ? sc : (sc.text || "")}</span>
            </div>
          ))}
        </div>
      )}
      {/* Claim-Button entfernt (User-Direktive 17.06.2026: Klick auf Kachel oeffnet Detail-Panel) */}
    </div>
  )
}

// ─────────────── Tasks View (Liste mit Parent/Child) ───────────────
const PHASE_FILTERS = [
  { key: "triage",      label: "Triage" },
  { key: "go",          label: "GO" },
  { key: "in_progress", label: "In Progress" },
  { key: "review",      label: "Review" },
  { key: "block",       label: "Block" },
  { key: "done",        label: "Done" },
  { key: "waiting",     label: "Waiting" },
]

function TasksView({ projectId, onSelectTask, onUserInputClick }: {
  projectId: string
  onSelectTask: (id: string) => void
  onUserInputClick: (id: string) => void
}) {
  const qc = useQueryClient()
  const { data: tasksData, refetch } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId, limit: 500 }),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  })
  const tasks: any[] = (tasksData as any)?.items || []

  // === Delete-Mutation (User-Direktive 16.06.2026) ===
  const deleteMut = useMutation({
    mutationFn: (taskId: string) => api.deleteTask(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks", projectId] }),
  })
  function deleteTaskWithConfirm(taskId: string, title: string, hasChildren: boolean) {
    const childWarn = hasChildren ? "\n\n⚠️ ACHTUNG: Alle Sub-Tasks werden mit gelöscht!" : ""
    const msg = `Task "${title}" wirklich LÖSCHEN?\n\nID: ${taskId}\n\nDiese Aktion kann nicht rückgängig gemacht werden.${childWarn}`
    if (window.confirm(msg)) {
      deleteMut.mutate(taskId)
    }
  }

  // Filter-State
  const [phaseFilter, setPhaseFilter] = useState<Set<string>>(new Set())  // leer = alle
  const [agentFilter, setAgentFilter] = useState<string>("")  // leer = alle

  // Verfuegbare Agenten dynamisch aus den Tasks ableiten
  const availableAgents: string[] = Array.from(new Set(
    tasks.map((t: any) => t.assigned_role).filter((r: any) => r && r.trim() !== "")
  )).sort()

  // Filter anwenden (nur auf Parents, Children werden unter Parent mit angezeigt)
  const filteredTasks = tasks.filter((t: any) => {
    // === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    // DB-Status "todo" entspricht der Anzeige-Spalte "GO" (siehe status_labels.py).
    // Daher normalisieren wir den Status-Key, damit der Filter korrekt funktioniert.
    const normalizedStatus = t.status === "todo" ? "go" : t.status
    if (phaseFilter.size > 0 && !phaseFilter.has(normalizedStatus)) return false
    if (agentFilter && t.assigned_role !== agentFilter) return false
    return true
  })

  const parents = filteredTasks.filter((t: any) => !t.parent_id)
  const childMap: Record<string, any[]> = {}
  for (const t of filteredTasks) {
    if (t.parent_id) {
      (childMap[t.parent_id] ||= []).push(t)
    }
  }

  function togglePhase(phase: string) {
    setPhaseFilter((prev) => {
      const next = new Set(prev)
      if (next.has(phase)) next.delete(phase)
      else next.add(phase)
      return next
    })
  }

  function clearFilters() {
    setPhaseFilter(new Set())
    setAgentFilter("")
  }

  const hasFilters = phaseFilter.size > 0 || agentFilter !== ""
  const filterCount = phaseFilter.size + (agentFilter ? 1 : 0)

  return (
    <div>
      {/* Button-Zeile mit Re-generate + Filtern */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <button className="btn btn-sm">
          <RotateCcw size={12} /> Re-generate Tasks
        </button>

        {/* Phasen-Filter: Toggle-Buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, paddingLeft: 8, borderLeft: "1px solid var(--color-hermes-border)" }}>
          <Filter size={12} color="var(--color-hermes-text-secondary)" />
          <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Phase:</span>
          {PHASE_FILTERS.map((p) => {
            const active = phaseFilter.has(p.key)
            return (
              <button
                key={p.key}
                className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                onClick={() => togglePhase(p.key)}
                style={{ fontSize: 10, padding: "2px 8px" }}
                title={`Filter: ${p.label}`}
              >
                {p.label}
              </button>
            )
          })}
        </div>

        {/* Agent-Filter: Dropdown */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, paddingLeft: 8, borderLeft: "1px solid var(--color-hermes-border)" }}>
          <Users size={12} color="var(--color-hermes-text-secondary)" />
          <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Agent:</span>
          <select
            className="select"
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            style={{ fontSize: 11, padding: "2px 6px" }}
            title="Nach Agent filtern"
          >
            <option value="">Alle Agenten</option>
            {availableAgents.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </div>

        {hasFilters && (
          <button className="btn btn-sm" onClick={clearFilters} title="Filter zuruecksetzen">
            <X size={10} /> Reset
          </button>
        )}

        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
          {filteredTasks.length} / {tasks.length} tasks · {parents.length} parent · {filteredTasks.length - parents.length} children
          {hasFilters && <span style={{ color: "var(--color-hermes-accent)" }}> · {filterCount} Filter aktiv</span>}
        </span>
      </div>

      {filteredTasks.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          {hasFilters
            ? <>Keine Tasks passen zu den Filtern. <button className="btn btn-sm" onClick={clearFilters} style={{ marginLeft: 8 }}>Filter zuruecksetzen</button></>
            : <>Keine Parent-Tasks. Lege einen mit "New Task" an.</>}
        </div>
      ) : parents.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          {hasFilters
            ? <>Filter zeigt nur Children ohne Parent. <button className="btn btn-sm" onClick={clearFilters} style={{ marginLeft: 8 }}>Filter zuruecksetzen</button></>
            : "Keine Parent-Tasks. Lege einen mit \"New Task\" an."}
        </div>
      ) : (
        <div>
          {parents.map((p: any) => (
            <ParentTaskRow
              key={p.id}
              parent={p}
              children={childMap[p.id] || []}
              onSelect={onSelectTask}
              onDelete={(id, hasChildren) => deleteTaskWithConfirm(id, p.title, hasChildren)}
              isDeleting={deleteMut.isPending && deleteMut.variables === p.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ParentTaskRow({
  parent, children, onSelect, onDelete, isDeleting,
}: {
  parent: any
  children: any[]
  onSelect: (id: string) => void
  onDelete: (id: string, hasChildren: boolean) => void
  isDeleting?: boolean
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="card mb-2" style={{ opacity: isDeleting ? 0.5 : 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <button className="btn btn-sm" style={{ padding: "0 4px" }} onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <span className="id-badge">{parent.id.slice(0, 12)}</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
          <Flame size={11} color={parent.priority >= 80 ? "var(--color-hermes-danger)" : "var(--color-hermes-accent-orange)"} />
          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{parent.priority}</span>
        </div>
      </div>
      <div style={{ fontWeight: 600, marginBottom: 4, cursor: "pointer" }} onClick={() => onSelect(parent.id)}>
        {parent.title}
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
        <span className="badge badge-orange">{parent.status}</span>
        {parent.assigned_role && <span className="badge badge-blue">💻 {parent.assigned_role}</span>}
        {parent.level && <span className="badge badge-gray">Level {parent.level}</span>}
        {/* Loeschen-Button (User-Direktive 16.06.2026) */}
        <button
          className="btn btn-sm"
          style={{ marginLeft: "auto", padding: "1px 6px", fontSize: 10 }}
          onClick={(e) => {
            e.stopPropagation()
            onDelete(parent.id, children.length > 0)
          }}
          disabled={isDeleting}
          title="Task endgültig löschen (inkl. Sub-Tasks & History)"
        >
          <Trash2 size={10} /> Löschen
        </button>
      </div>

      {open && children.length > 0 && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--color-hermes-border)" }}>
          {children.map((c: any) => (
            <div key={c.id} className="subtask-item" onClick={() => onSelect(c.id)} style={{ cursor: "pointer" }}>
              <CheckCircle2 size={12} color={c.status === "done" ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)"} />
              <span className="id-badge id-badge-child">{c.id.slice(0, 8)}</span>
              <span style={{ flex: 1 }}>{c.title}</span>
              <span className="badge badge-gray" style={{ fontSize: 9 }}>— {c.id.slice(0, 4)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────── Task Detail Panel (slide-in) ───────────────
// ─────────────── New Project Modal ───────────────
function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (p: any) => void }) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("new_request")
  const createMut = useMutation({
    mutationFn: () => api.createProject({ name, description, category }),
    onSuccess: (p: any) => onCreated(p),
  })

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 16px", fontSize: 15 }}>Neues Projekt</h3>
        <input className="input mb-2" placeholder="Projekt-Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <textarea className="input mb-2" placeholder="Beschreibung" value={description} onChange={(e) => setDescription(e.target.value)} style={{ minHeight: 60 }} />
        <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="new_request">new_request</option>
          <option value="ticket">ticket</option>
          <option value="change">change</option>
        </select>
        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={() => createMut.mutate()} disabled={!name || createMut.isPending}>
            {createMut.isPending ? "Erstelle…" : "Erstellen"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────── KPIs View ───────────────
function KpisView({ projectId }: { projectId: string }) {
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId, limit: 500 }),
  })
  const tasks: any[] = (tasksData as any)?.items || []
  const total = tasks.length
  const done = tasks.filter((t: any) => t.status === "done").length
  const inProgress = tasks.filter((t: any) => t.status === "in_progress").length
  const cost = tasks.reduce((sum: number, t: any) => sum + (t.total_cost_usd || 0), 0)

  return (
    <div>
      <div className="page-header">
        <h1>KPIs</h1>
        <p>Projekt-Kennzahlen</p>
      </div>
      <div className="card-grid">
        <div className="stat-card">
          <span className="label">Tasks Gesamt</span>
          <span className="value">{total}</span>
        </div>
        <div className="stat-card">
          <span className="label">Done</span>
          <span className="value" style={{ color: "var(--color-hermes-accent)" }}>{done}</span>
        </div>
        <div className="stat-card">
          <span className="label">In Progress</span>
          <span className="value" style={{ color: "var(--color-hermes-accent-blue)" }}>{inProgress}</span>
        </div>
        <div className="stat-card">
          <span className="label">Gesamtkosten</span>
          <span className="value" style={{ color: "var(--color-hermes-danger)" }}>${cost.toFixed(4)}</span>
        </div>
      </div>
    </div>
  )
}

function PlaceholderTab({ title, hint }: { title: string; hint: string }) {
  return (
    <div>
      <div className="page-header">
        <h1>{title}</h1>
      </div>
      <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
        <AlertCircle size={24} style={{ marginBottom: 8 }} />
        <p style={{ margin: 0 }}>{hint}</p>
      </div>
    </div>
  )
}

function RequirementsTabPlaceholder({ projectId, projectName }: { projectId: string; projectName: string }) {
  const { data: reqs } = useQuery({
    queryKey: ["requirements", projectId],
    queryFn: () => api.listRequirements(projectId),
  })
  const list: any[] = (reqs as any) || []
  return (
    <div>
      <div className="page-header">
        <h1>Requirements</h1>
        <p>Anforderungen fuer {projectName}</p>
      </div>
      {list.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          <AlertCircle size={24} style={{ marginBottom: 8 }} />
          <p style={{ margin: 0 }}>
            Noch keine Requirements. Starte im <strong>Brainstorm</strong>-Tab und klicke am Ende auf
            <strong> Generate Requirements</strong>.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {list.map((r: any) => (
            <div key={r.id} className="card">
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span className="badge badge-blue">v{r.version || 1}</span>
                <span className="text-xs text-dim">{r.ts ? new Date(r.ts).toLocaleString("de-DE") : "—"}</span>
              </div>
              <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}>{r.content}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// =====================================================
//  UserInputModal — User-Direktive 17.06.2026
//  Oeffnet ein Modal mit der offenen AgentQuestion zum aktuellen Task.
//  User beantwortet direkt hier, Status wechselt zu in_progress.
// =====================================================
function UserInputModal({ taskId, onClose, onAnswered }: {
  taskId: string
  onClose: () => void
  onAnswered: () => void
}) {
  const qc = useQueryClient()
  const [text, setText] = useState("")

  const { data: task } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId),
  })

  const { data: questionsData, isLoading: questionsLoading } = useQuery({
    queryKey: ["agent-questions", "by-task", taskId],
    queryFn: () => api.agentQuestions.list({ status: "pending", limit: 50 }),
  })
  const questions: any[] = ((questionsData as any)?.items || []).filter(
    (q: any) => {
      const ctx = q.context
      if (!ctx) return false
      return ctx.task_id === taskId
    }
  )
  // DEBUG: Console-Log, damit der User sehen kann, was passiert
  useEffect(() => {
    console.log(`[UserInputModal] taskId=${taskId} | questionsLoading=${questionsLoading} | questions.length=${questions.length} | input_q_id=${task?.meta?.input_question_id}`)
    if (questions.length > 0) {
      console.log(`[UserInputModal] First question: ${questions[0].id} | title: ${questions[0].title}`)
    }
  }, [taskId, questionsLoading, questions.length, task])

  const answerMut = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.agentQuestions.answer(id, { answer_text: text, answered_by: "user" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-questions"] })
      qc.invalidateQueries({ queryKey: ["agent-questions-pending"] })
      onAnswered()
    },
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => api.agentQuestions.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-questions"] })
      qc.invalidateQueries({ queryKey: ["agent-questions-pending"] })
      onClose()
    },
  })

  const [selectedQId, setSelectedQId] = useState<string | null>(null)
  useEffect(() => {
    if (questions.length > 0 && !selectedQId) {
      setSelectedQId(questions[0].id)
    }
  }, [questions, selectedQId])

  const currentQ = questions.find((q: any) => q.id === selectedQId)

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--color-hermes-bg, #0f0f0f)",
          border: "1px solid var(--color-hermes-accent, #7c3aed)",
          borderRadius: 10, padding: 20, maxWidth: 720, width: "92%",
          maxHeight: "88vh", overflowY: "auto",
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <HelpCircle size={22} color="var(--color-hermes-accent, #7c3aed)" />
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>User-Input erforderlich</h2>
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary, #999)" }}>
              {task?.title || `Task ${taskId.slice(0, 8)}`}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#999", cursor: "pointer", padding: 4 }}
            title="Schliessen"
          >
            <X size={18} />
          </button>
        </div>

        {questionsLoading ? (
          <div style={{
            background: "rgba(0,0,0,0.2)", border: "1px solid #555",
            borderRadius: 6, padding: 20, textAlign: "center", color: "#999",
          }}>
            <Loader2 size={20} className="spin" style={{ marginBottom: 6 }} />
            <div>Lade offene Fragen fuer diesen Task...</div>
          </div>
        ) : questions.length === 0 ? (
          <div style={{
            background: "rgba(0,0,0,0.2)", border: "1px dashed #555",
            borderRadius: 6, padding: 20, textAlign: "center", color: "#999",
          }}>
            <CheckCircle2 size={20} style={{ marginBottom: 6 }} color="#10b981" />
            <div>Keine offenen Fragen fuer diesen Task.</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>
              Der Agent hat aktuell keinen Input-Bedarf. Du kannst das Modal schliessen.
            </div>
            <div style={{ fontSize: 10, marginTop: 8, color: "#666" }}>
              Task-ID: {taskId} | input_question_id: {task?.meta?.input_question_id || "keine"}
            </div>
          </div>
        ) : questions.length > 1 ? (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#999", marginBottom: 6 }}>
              {questions.length} offene Fragen — waehle eine aus:
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {questions.map((q: any) => (
                <button
                  key={q.id}
                  onClick={() => setSelectedQId(q.id)}
                  style={{
                    background: selectedQId === q.id ? "rgba(124, 58, 237, 0.15)" : "rgba(0,0,0,0.2)",
                    border: `1px solid ${selectedQId === q.id ? "var(--color-hermes-accent, #7c3aed)" : "#333"}`,
                    color: "var(--color-hermes-text, #e5e5e5)",
                    padding: "8px 12px", borderRadius: 4, fontSize: 12,
                    textAlign: "left", cursor: "pointer",
                  }}
                >
                  <strong>{q.title}</strong>
                  <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
                    {q.agent_label || q.agent_id}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {currentQ && (
          <>
            <UserInputForm
              question={currentQ}
              isSubmitting={answerMut.isPending}
              onSubmit={async (text) => {
                answerMut.mutate({ id: currentQ.id, text })
              }}
            />

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                onClick={() => {
                  if (confirm("Frage stornieren?")) cancelMut.mutate(currentQ.id)
                }}
                disabled={cancelMut.isPending}
                style={{
                  background: "transparent", color: "#6b7280", border: "1px solid #6b7280",
                  borderRadius: 6, padding: "10px 16px", fontSize: 14,
                  cursor: "pointer",
                }}
              >
                Stornieren
              </button>
              <button
                onClick={onClose}
                style={{
                  background: "transparent", color: "#999", border: "1px solid #444",
                  borderRadius: 6, padding: "10px 16px", fontSize: 14,
                  cursor: "pointer", marginLeft: "auto",
                }}
              >
                Spaeter
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
