import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import {
  Activity, Server, Cpu, HardDrive, Database, FolderOpen, FolderGit,
  Container, CheckCircle2, XCircle, RefreshCw, Star, GitFork,
  ChevronDown, ChevronRight, Boxes,
} from "lucide-react"
import ProjectDetailModal from "../components/ProjectDetailModal"

interface StatusProject {
  id: string
  name: string
  project_number: string | null
  github_url: string | null
  local_path: string | null
  local_available: boolean
  container_image: string | null
  container_port: number | null
  container_status: string | null
  task_count: number
  tasks_open: number
  tasks_done: number
  tasks_cancelled: number
  github_stars?: number
  github_forks?: number
}

interface StatusContainer {
  id?: number
  name: string
  image: string | null
  port_external: string | null
  port_internal: number | null
  network: string | null
  ip: string | null
  status: string | null
  category: string | null
  component_id?: number | null
  component_slug?: string | null
  component_name?: string | null
  project_id?: string | null
  project_name?: string | null
  project_number?: string | null
}

interface ContainerGroup {
  project_id: string | null
  project_name: string
  project_number: string | null
  container_count: number
  healthy_count: number
  running_count: number
  containers: StatusContainer[]
  components: Record<string, { slug: string | null; name: string; container_count: number; containers: StatusContainer[] }>
}

interface ContainerResponse {
  groups: ContainerGroup[]
  total_containers: number
  group_count: number
}

interface ServiceRepo {
  id: number
  name: string
  local_path: string | null
  github_url: string
  local_available: boolean
  category: string | null
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return "gerade eben"
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`
  return `${Math.floor(diff / 86400000)}d`
}

export default function Status() {
  const queryClient = useQueryClient()
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  // Welche Container-Apps aufgeklappt sind (default: alle zu)
  const [expandedApps, setExpandedApps] = useState<Record<string, boolean>>({})

  // === Daten laden ===
  const systemQuery = useQuery({
    queryKey: ["status", "system"],
    queryFn: async () => {
      const r = await fetch("/api/status/system")
      if (!r.ok) throw new Error("system")
      return r.json()
    },
  })

  const projectsQuery = useQuery({
    queryKey: ["status", "projects"],
    queryFn: async () => {
      const r = await fetch("/api/status/projects")
      if (!r.ok) throw new Error("projects")
      const data = await r.json()
      // Nur AKTIVE Projekte (keine archivierten)
      return (data as StatusProject[]).filter(
        (p: any) => p.status !== "archived" && p.status !== "closed"
      )
    },
    refetchInterval: 30000,
  })

  const containersQuery = useQuery({
    queryKey: ["status", "containers"],
    queryFn: async () => {
      const r = await fetch("/api/status/containers")
      if (!r.ok) throw new Error("containers")
      const data = await r.json()
      // Server liefert entweder gruppiert (mit groups-Key) oder flache Liste
      if (data && typeof data === "object" && "groups" in data) {
        return data as ContainerResponse
      }
      // Fallback: flache Liste in "Infrastruktur" gruppieren
      const list = data as StatusContainer[]
      return {
        groups: [{
          project_id: null,
          project_name: "Container (nicht zugeordnet)",
          project_number: null,
          container_count: list.length,
          healthy_count: list.filter(c => c.status === "healthy" || c.status === "running").length,
          running_count: list.filter(c => c.status === "running").length,
          containers: list,
          components: { _flat: { slug: null, name: "Alle", container_count: list.length, containers: list } },
        }],
        total_containers: list.length,
        group_count: 1,
      }
    },
    refetchInterval: 60000,
  })

  const reposQuery = useQuery({
    queryKey: ["status", "repos"],
    queryFn: async () => {
      const r = await fetch("/api/status/service-repos")
      if (!r.ok) throw new Error("repos")
      return (await r.json()) as ServiceRepo[]
    },
    refetchInterval: 60000,
  })

  const sopLogsQuery = useQuery({
    queryKey: ["status", "sop-logs"],
    queryFn: async () => {
      const r = await fetch("/api/status/sop-logs/recent?limit=10")
      if (!r.ok) throw new Error("sop-logs")
      return r.json()
    },
    refetchInterval: 15000,
  })

  const projects = projectsQuery.data || []
  const containerData: ContainerResponse | { groups: []; total_containers: 0; group_count: 0 } =
    containersQuery.data || { groups: [], total_containers: 0, group_count: 0 }
  const repos = reposQuery.data || []
  const sopLogs = sopLogsQuery.data || []

  return (
    <div style={{ padding: 10 }}>
      <div className="page-header" style={{ marginBottom: 12 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>Status</h1>
        <p style={{ fontSize: 11, margin: "4px 0 0", color: "var(--color-hermes-text-secondary)" }}>
          System-Health · Projekte (mit Components) · Container · SOP-Logs
        </p>
      </div>

      {/* === SPALTE 1: SYSTEM === */}
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr 320px", gap: 12 }}>
        <div className="card" style={{ minHeight: 500 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <Activity size={13} color="var(--color-hermes-accent)" />
            <h2 style={{ fontSize: 13, margin: 0 }}>System</h2>
          </div>
          {systemQuery.isLoading ? (
            <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              Lade System-Status...
            </div>
          ) : systemQuery.error ? (
            <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--color-hermes-danger)" }}>
              Backend nicht erreichbar
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <SystemStat icon={<Server size={11} />} label="Backend" value="Online" sub="127.0.0.1:9220" color="green" />
              <SystemStat icon={<Database size={11} />} label="DB" value="SQLite" sub={`${systemQuery.data?.tables || "?"} Tabellen`} color="green" />
              <SystemStat icon={<Container size={11} />} label="Container" value={`${containerData.total_containers}`} sub={`${containerData.group_count} Apps`} color="green" />
              <SystemStat icon={<FolderOpen size={11} />} label="Projekte" value={`${projects.length}`} sub="aktiv" color="green" />
              <SystemStat icon={<Cpu size={11} />} label="SOP-Worker" value={systemQuery.data?.worker?.running ? "running" : "stopped"} sub={systemQuery.data?.worker?.version || "—"} color={systemQuery.data?.worker?.running ? "green" : "orange"} />
              <SystemStat icon={<HardDrive size={11} />} label="Archiv" value={`${systemQuery.data?.archive?.total_tasks || 0}`} sub="historische Tasks" color="green" />
            </div>
          )}
        </div>

        {/* === SPALTE 2: PROJEKTE === */}
        <div className="card" style={{ minHeight: 500 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <FolderOpen size={13} color="var(--color-hermes-accent-blue)" />
            <h2 style={{ fontSize: 13, margin: 0 }}>Projekte</h2>
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>({projects.length})</span>
            <div style={{ flex: 1 }} />
            <button
              onClick={() => { projectsQuery.refetch(); containersQuery.refetch(); reposQuery.refetch() }}
              title="Alles aktualisieren"
              style={{
                background: "transparent", border: "1px solid var(--color-hermes-border)",
                color: "var(--color-hermes-text-secondary)", borderRadius: 4,
                padding: "2px 6px", fontSize: 10, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 3,
              }}
            >
              <RefreshCw size={10} /> refresh
            </button>
          </div>

          {projectsQuery.isLoading ? (
            <div style={{ padding: 20, textAlign: "center" }}>Lade Projekte...</div>
          ) : projects.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center" }}>Keine aktiven Projekte</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {projects.map((p) => (
                <ProjectTile
                  key={p.id}
                  project={p}
                  onClick={() => setSelectedProjectId(p.id)}
                  onUpdateSuccess={() => queryClient.invalidateQueries({ queryKey: ["status", "projects"] })}
                />
              ))}
            </div>
          )}
        </div>

        {/* === SPALTE 3: SOP-LOGS === */}
        <div className="card" style={{ minHeight: 500 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <Activity size={13} color="var(--color-hermes-accent-orange)" />
            <h2 style={{ fontSize: 13, margin: 0 }}>SOP-Logs</h2>
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>(letzte 10)</span>
          </div>
          {sopLogsQuery.isLoading ? (
            <div style={{ padding: 20, textAlign: "center", fontSize: 11 }}>Lade...</div>
          ) : sopLogs.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              Keine SOP-Aktivitaeten
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {sopLogs.map((log: any, i: number) => (
                <div key={i} style={{
                  padding: "6px 8px", background: "var(--color-hermes-muted)",
                  borderRadius: 4, fontSize: 10, borderLeft: "2px solid var(--color-hermes-accent)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                    <span style={{ fontWeight: 600 }}>{log.sop_name || log.sop_id}</span>
                    <span style={{ color: "var(--color-hermes-text-secondary)" }}>{timeAgo(log.timestamp)}</span>
                  </div>
                  <div style={{ color: "var(--color-hermes-text-secondary)" }}>
                    {log.step_name || log.event || "—"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* === UNTERE REIHE: CONTAINER + SERVICE-REPOS === */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        {/* Container (gruppiert nach App) */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <Container size={13} color="var(--color-hermes-accent)" />
            <h2 style={{ fontSize: 13, margin: 0 }}>Container ({containerData.total_containers})</h2>
            <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>
              · {containerData.group_count} Apps
            </span>
          </div>
          {containerData.groups.length === 0 ? (
            <div style={{ padding: 12, fontSize: 11, color: "var(--color-hermes-text-secondary)", textAlign: "center" }}>
              Keine Container erfasst
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {containerData.groups.map((app) => {
                const appKey = app.project_id || "_infra"
                const isOpen = expandedApps[appKey] ?? false
                const allGood = app.healthy_count === app.container_count
                return (
                  <div key={appKey} style={{
                    border: "1px solid var(--color-hermes-border)",
                    borderRadius: 4,
                    overflow: "hidden",
                  }}>
                    {/* App-Header (klickbar) */}
                    <div
                      onClick={() => setExpandedApps({ ...expandedApps, [appKey]: !isOpen })}
                      style={{
                        padding: "6px 10px",
                        background: app.project_id
                          ? "rgba(124,58,237,0.1)"
                          : "rgba(88,166,255,0.06)",
                        cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 6,
                        userSelect: "none",
                      }}
                    >
                      {isOpen
                        ? <ChevronDown size={12} color="var(--color-hermes-accent-blue)" />
                        : <ChevronRight size={12} color="var(--color-hermes-text-secondary)" />}
                      <Boxes size={12} color={app.project_id ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text-secondary)"} />
                      <span style={{ fontWeight: 600, fontSize: 12, flex: 1 }}>
                        {app.project_name}
                      </span>
                      {app.project_number && (
                        <span style={{
                          fontSize: 9, padding: "1px 5px", borderRadius: 3,
                          background: "rgba(124,58,237,0.15)", color: "var(--color-hermes-accent-blue)",
                        }}>{app.project_number}</span>
                      )}
                      <span style={{
                        fontSize: 10, padding: "2px 6px", borderRadius: 3,
                        background: allGood ? "rgba(46,160,67,0.15)" : "rgba(220,38,38,0.15)",
                        color: allGood ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)",
                        fontWeight: 600,
                      }}>
                        {app.healthy_count}/{app.container_count} ok
                      </span>
                    </div>

                    {/* Container-Liste (aufgeklappt) */}
                    {isOpen && (
                      <div style={{ padding: 6, display: "flex", flexDirection: "column", gap: 6 }}>
                        {/* Pro Component eine Sub-Group */}
                        {Object.entries(app.components).map(([compKey, comp]) => (
                          <div key={compKey}>
                            {comp.slug && (
                              <div style={{
                                fontSize: 9, color: "var(--color-hermes-text-secondary)",
                                marginBottom: 3, paddingLeft: 4,
                                textTransform: "uppercase", letterSpacing: 0.5,
                              }}>
                                <Boxes size={9} style={{ verticalAlign: -1, marginRight: 3 }} />
                                {comp.name} ({comp.container_count})
                              </div>
                            )}
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              {comp.containers.map((c) => (
                                <div key={c.name} style={{
                                  padding: "4px 8px", background: "var(--color-hermes-muted)",
                                  borderRadius: 3, fontSize: 11, borderLeft: "2px solid var(--color-hermes-accent)",
                                  display: "flex", alignItems: "center", gap: 6,
                                }}>
                                  <span style={{ fontWeight: 600 }}>🐳 {c.name}</span>
                                  <span style={{ color: "var(--color-hermes-text-secondary)", fontSize: 10 }}>
                                    {c.port_external || "—"}
                                  </span>
                                  <div style={{ flex: 1 }} />
                                  <span style={{
                                    fontSize: 9, padding: "1px 4px", borderRadius: 3,
                                    color: c.status === "healthy" || c.status === "running"
                                      ? "var(--color-hermes-accent)"
                                      : "var(--color-hermes-danger)",
                                  }}>
                                    ● {c.status}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Service-Repos */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <FolderGit size={13} color="var(--color-hermes-accent-blue)" />
            <h2 style={{ fontSize: 13, margin: 0 }}>Service-Repos ({repos.length})</h2>
          </div>
          {repos.length === 0 ? (
            <div style={{ padding: 12, fontSize: 11, color: "var(--color-hermes-text-secondary)", textAlign: "center" }}>
              Keine verknuepften Service-Repos
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {repos.map((r) => (
                <div key={r.id} style={{
                  padding: "5px 8px", background: "var(--color-hermes-muted)",
                  borderRadius: 4, fontSize: 11, borderLeft: "2px solid var(--color-hermes-accent-blue)",
                  display: "flex", alignItems: "center", gap: 8,
                }}>
                  {r.local_available
                    ? <CheckCircle2 size={10} color="var(--color-hermes-accent)" />
                    : <XCircle size={10} color="var(--color-hermes-danger)" />}
                  <span style={{ fontWeight: 600 }}>{r.name}</span>
                  <span style={{ color: "var(--color-hermes-text-secondary)", fontSize: 9 }}>
                    {r.category}
                  </span>
                  <div style={{ flex: 1 }} />
                  <a href={r.github_url} target="_blank" rel="noopener noreferrer"
                     onClick={(e) => e.stopPropagation()}
                     style={{ color: "var(--color-hermes-accent-blue)", fontSize: 9, textDecoration: "none" }}>
                    GitHub →
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* === Modal: Project Details === */}
      {selectedProjectId && (
        <ProjectDetailModal
          projectId={selectedProjectId}
          onClose={() => setSelectedProjectId(null)}
          onUpdated={() => {
            queryClient.invalidateQueries({ queryKey: ["status", "projects"] })
            queryClient.invalidateQueries({ queryKey: ["status", "containers"] })
          }}
        />
      )}
    </div>
  )
}

// === Sub-Component: ProjectTile (klickbar + Update-Button) ===
function ProjectTile({
  project: p,
  onClick,
  onUpdateSuccess,
}: {
  project: StatusProject
  onClick: () => void
  onUpdateSuccess: () => void
}) {
  const queryClient = useQueryClient()
  const [updating, setUpdating] = useState(false)

  const updateGitHub = useMutation({
    mutationFn: async () => {
      const r = await fetch(`/api/status/projects/${p.id}/github-update`, { method: "POST" })
      if (!r.ok) throw new Error("update failed")
      return r.json()
    },
    onSuccess: () => {
      onUpdateSuccess()
      queryClient.invalidateQueries({ queryKey: ["status", "projects"] })
    },
    onSettled: () => setUpdating(false),
  })

  const handleUpdate = (e: React.MouseEvent) => {
    e.stopPropagation()
    setUpdating(true)
    updateGitHub.mutate()
  }

  return (
    <div
      onClick={onClick}
      style={{
        padding: 10,
        border: "1px solid var(--color-hermes-border)",
        borderRadius: 6,
        background: p.local_available
          ? "rgba(46,160,67,0.05)"
          : "rgba(220,38,38,0.05)",
        cursor: "pointer",
        transition: "transform 0.1s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-1px)"
        e.currentTarget.style.borderColor = "var(--color-hermes-accent-blue)"
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)"
        e.currentTarget.style.borderColor = "var(--color-hermes-border)"
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <FolderOpen size={13} color="var(--color-hermes-accent-blue)" />
        <span style={{ fontWeight: 600, fontSize: 13 }}>{p.name}</span>
        {p.project_number && (
          <span style={{
            fontSize: 9, padding: "1px 5px", borderRadius: 3,
            background: "rgba(124,58,237,0.15)", color: "var(--color-hermes-accent-blue)",
          }}>
            {p.project_number}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={handleUpdate}
          disabled={updating}
          title="GitHub-Daten aktualisieren (Stars, Forks, etc.)"
          style={{
            background: "rgba(88,166,255,0.15)", border: "1px solid rgba(88,166,255,0.3)",
            color: "var(--color-hermes-accent-blue)", borderRadius: 4,
            padding: "1px 5px", fontSize: 9, cursor: updating ? "wait" : "pointer",
            display: "flex", alignItems: "center", gap: 3, opacity: updating ? 0.6 : 1,
          }}
        >
          <RefreshCw size={9} className={updating ? "spin" : ""} />
          {updating ? "update..." : "updaten"}
        </button>
        {p.local_available ? (
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--color-hermes-accent)", fontWeight: 600 }}>
            <CheckCircle2 size={10} /> lokal
          </span>
        ) : (
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--color-hermes-danger)", fontWeight: 600 }}>
            <XCircle size={10} /> fehlt
          </span>
        )}
      </div>
      {p.github_url && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, marginBottom: 3 }}>
          <FolderGit size={9} />
          <a href={p.github_url} target="_blank" rel="noopener noreferrer"
             onClick={(e) => e.stopPropagation()}
             style={{ color: "var(--color-hermes-accent-blue)", textDecoration: "none", flex: 1, wordBreak: "break-all" }}>
            {p.github_url.replace("https://github.com/", "")}
          </a>
          {(p.github_stars || 0) > 0 && (
            <span style={{ display: "flex", alignItems: "center", gap: 2, color: "var(--color-hermes-text-secondary)" }}>
              <Star size={9} color="#facc15" /> {p.github_stars}
            </span>
          )}
          {(p.github_forks || 0) > 0 && (
            <span style={{ display: "flex", alignItems: "center", gap: 2, color: "var(--color-hermes-text-secondary)" }}>
              <GitFork size={9} /> {p.github_forks}
            </span>
          )}
        </div>
      )}
      {p.local_path && (
        <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginBottom: 3 }}>
          📁 <code style={{ background: "rgba(0,0,0,0.1)", padding: "1px 4px", borderRadius: 3 }}>{p.local_path}</code>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 4, fontSize: 9 }}>
        <span style={{ color: "var(--color-hermes-text-secondary)" }}>
          <strong style={{ color: "var(--color-hermes-text)" }}>{p.task_count}</strong> Tasks
        </span>
        <span style={{ color: "var(--color-hermes-accent)" }}>
          <strong>{p.tasks_open}</strong> aktiv
        </span>
        <span style={{ color: "var(--color-hermes-accent)" }}>
          <strong>{p.tasks_done}</strong> done
        </span>
        <span style={{ color: "var(--color-hermes-text-secondary)" }}>
          <strong>{p.tasks_cancelled}</strong> cancelled
        </span>
      </div>
    </div>
  )
}

// === Sub-Component: SystemStat ===
function SystemStat({
  icon, label, value, sub, color,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub: string
  color: "green" | "orange" | "red"
}) {
  const colors = {
    green: "var(--color-hermes-accent)",
    red: "var(--color-hermes-danger)",
    orange: "var(--color-hermes-accent-orange)",
  }
  return (
    <div style={{
      padding: 8,
      background: "var(--color-hermes-muted)",
      borderRadius: 4,
      borderLeft: `3px solid ${colors[color]}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3 }}>
        <span style={{ color: colors[color] }}>{icon}</span>
        <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase" }}>
          {label}
        </span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-hermes-text)" }}>{value}</div>
      <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 1 }}>{sub}</div>
    </div>
  )
}