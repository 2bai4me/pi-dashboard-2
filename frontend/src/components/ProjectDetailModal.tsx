// ProjectDetailModal.tsx (User-Direktive 24.06.2026, Status-Seite)
// Modal mit allen Details zu einem GitHub-Projekt (Stars, Forks, Container, Findings, Tasks)
// Hat einen "GitHub aktualisieren"-Button.

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  X, Star, GitFork, FolderGit, FolderOpen, Container,
  CheckCircle2, XCircle, RefreshCw, Database, ExternalLink, Clock,
  AlertTriangle, FileText, Hash, Boxes, Check,
} from "lucide-react"
import { api } from "../api"

interface ProjectDetail {
  id: string
  name: string
  project_number: string | null
  description: string | null
  category?: string | null
  mode?: string | null
  status: string
  github_url: string | null
  github_data: any | null
  github_stars: number
  github_forks: number
  github_default_branch: string | null
  github_size_kb: number
  github_license: string | null
  github_topics: string[]
  github_language: string | null
  github_fetched_at: string | null
  local_path: string | null
  local_available: boolean
  container_image: string | null
  container_port: number | null
  container_status: string | null
  critical_findings: Record<string, any> | null
  task_count: number
  tasks: Array<{
    id: string; title: string; status: string; priority: number; created_at: string | null
  }>
  components?: Array<{
    id: number
    slug: string
    name: string
    type: string | null
    description: string | null
    container_image: string | null
    container_port: number | null
    container_status: string | null
    container_name: string | null
    local_path: string | null
    github_url: string | null
    container_count: number
  }>
}

interface ProjectDetailModalProps {
  projectId: string
  onClose: () => void
  onUpdated?: () => void
}

export default function ProjectDetailModal({ projectId, onClose, onUpdated }: ProjectDetailModalProps) {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<"overview" | "components" | "container" | "findings" | "tasks">("overview")
  const [updateResult, setUpdateResult] = useState<any>(null)

  // === Project Details laden ===
  const detailsQuery = useQuery({
    queryKey: ["status", "project-details", projectId],
    queryFn: () => fetch(`/api/status/projects/${projectId}/details`).then(r => r.json()).catch(() => null),
    enabled: !!projectId,
  })
  const project: ProjectDetail | null = detailsQuery.data

  // === GitHub-Update-Mutation ===
  const updateMut = useMutation({
    mutationFn: () => fetch(`/api/status/projects/${projectId}/github-update`, { method: "POST" }).then(r => r.json()),
    onSuccess: (data) => {
      setUpdateResult(data)
      // Cache invalidieren
      qc.invalidateQueries({ queryKey: ["status", "project-details", projectId] })
      qc.invalidateQueries({ queryKey: ["status", "projects"] })
      if (onUpdated) onUpdated()
    },
  })

  function timeAgo(iso: string | null): string {
    if (!iso) return "—"
    try {
      const t = new Date(iso).getTime()
      const diff = (Date.now() - t) / 1000
      if (diff < 60) return `${Math.floor(diff)}s ago`
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
      return `${Math.floor(diff / 86400)}d ago`
    } catch { return iso }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 10001, padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--color-hermes-surface)",
          borderRadius: 8,
          border: "1px solid var(--color-hermes-border)",
          width: "min(800px, 95vw)",
          maxHeight: "90vh",
          display: "flex", flexDirection: "column",
          boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        }}
      >
        {/* === Header === */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
          borderBottom: "1px solid var(--color-hermes-border)",
        }}>
          <FolderGit size={20} color="var(--color-hermes-accent-blue)" />
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, flex: 1 }}>
            {detailsQuery.isLoading ? "Lade Details..." : project?.name || "Projekt"}
          </h2>
          {project?.project_number && (
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 4,
              background: "rgba(124,58,237,0.15)", color: "var(--color-hermes-accent-blue)",
            }}>
              {project.project_number}
            </span>
          )}
          <button
            onClick={() => updateMut.mutate()}
            disabled={updateMut.isPending || !project?.github_url}
            className="btn btn-sm"
            style={{
              background: "var(--color-hermes-accent-blue)", color: "#fff",
              fontWeight: 600, padding: "4px 12px",
            }}
            title="GitHub-API aufrufen und DB aktualisieren"
          >
            {updateMut.isPending ? (
              <><Clock size={12} /> Aktualisiere...</>
            ) : (
              <><RefreshCw size={12} /> GitHub aktualisieren</>
            )}
          </button>
          <button onClick={onClose} className="btn btn-sm" title="Schliessen (Esc)">
            <X size={14} />
          </button>
        </div>

        {/* === Tabs === */}
        <div style={{
          display: "flex", gap: 4, padding: "8px 16px 0",
          borderBottom: "1px solid var(--color-hermes-border)",
        }}>
          {([
            { key: "overview", label: "Uebersicht", icon: <Boxes size={12} /> },
            { key: "components", label: "Components", icon: <Boxes size={12} />, count: project?.components?.length },
            { key: "container", label: "Container", icon: <Container size={12} /> },
            { key: "findings", label: "Findings", icon: <AlertTriangle size={12} />, count: project?.critical_findings ? Object.keys(project.critical_findings).length : 0 },
            { key: "tasks", label: "Tasks", icon: <FileText size={12} />, count: project?.task_count },
          ] as const).map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`btn btn-sm ${activeTab === t.key ? "btn-primary" : ""}`}
              style={{ fontSize: 11, padding: "4px 10px", marginBottom: -1, borderRadius: "4px 4px 0 0" }}
            >
              {t.icon} {t.label}
              {"count" in t && t.count ? <span style={{ marginLeft: 4, opacity: 0.7 }}>({t.count})</span> : null}
            </button>
          ))}
        </div>

        {/* === Content === */}
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {detailsQuery.isLoading ? (
            <div style={{ textAlign: "center", padding: 40, color: "var(--color-hermes-text-secondary)" }}>
              <RefreshCw size={20} /> Lade Details...
            </div>
          ) : !project ? (
            <div style={{ textAlign: "center", padding: 40, color: "var(--color-hermes-danger)" }}>
              <XCircle size={20} /> Projekt nicht gefunden
            </div>
          ) : (
            <>
              {/* Update-Erfolg-Banner */}
              {updateResult?.success && (
                <div style={{
                  padding: 10, marginBottom: 12, borderRadius: 4,
                  background: "rgba(46,160,67,0.15)", border: "1px solid var(--color-hermes-accent)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <Check size={14} color="var(--color-hermes-accent)" />
                    <strong>GitHub aktualisiert</strong>
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                      {timeAgo(updateResult.fetched_at)}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                    Stars: {updateResult.stars} | Forks: {updateResult.forks} | Branch: {updateResult.default_branch} | Language: {updateResult.language} | Size: {updateResult.size_kb} KB
                  </div>
                </div>
              )}

              {/* === TAB: Uebersicht === */}
              {activeTab === "overview" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {/* GitHub-Sektion */}
                  <Section title="GitHub" icon={<FolderGit size={14} />}>
                    {project.github_url ? (
                      <>
                        <Row label="URL" value={
                          <a href={project.github_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--color-hermes-accent-blue)", textDecoration: "none" }}>
                            <ExternalLink size={10} style={{ verticalAlign: -1, marginRight: 3 }} />
                            {project.github_url.replace("https://github.com/", "")}
                          </a>
                        } />
                        {project.github_data?.description ? (
                          <Row label="Beschreibung" value={
                            <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                              {project.github_data.description}
                            </span>
                          } />
                        ) : null}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
                          <StatBadge icon={<Star size={12} color="#facc15" />} label="Stars" value={project.github_stars} />
                          <StatBadge icon={<GitFork size={12} />} label="Forks" value={project.github_forks} />
                          <StatBadge icon={<GitBranchIcon size={12} />} label="Branch" value={project.github_default_branch || "main"} />
                          <StatBadge icon={<Boxes size={12} />} label="Size" value={`${project.github_size_kb} KB`} />
                          <StatBadge icon={<FileText size={12} />} label="License" value={project.github_license || "none"} />
                          <StatBadge icon={<Boxes size={12} />} label="Language" value={project.github_language || "?"} />
                        </div>
                        {project.github_topics && project.github_topics.length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", marginBottom: 4 }}>
                              Topics
                            </div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                              {project.github_topics.map(t => (
                                <span key={t} style={{
                                  fontSize: 10, padding: "2px 6px", borderRadius: 3,
                                  background: "rgba(88,166,255,0.15)", color: "var(--color-hermes-accent-blue)",
                                }}>
                                  {t}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        <div style={{ marginTop: 8, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                          <Clock size={10} style={{ verticalAlign: -1, marginRight: 3 }} />
                          Zuletzt aktualisiert: {timeAgo(project.github_fetched_at)}
                        </div>
                      </>
                    ) : (
                      <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Kein GitHub-Repo verlinkt</div>
                    )}
                  </Section>

                  {/* Lokal-Sektion */}
                  {project.local_path && (
                    <Section title="Lokales Verzeichnis" icon={<FolderOpen size={14} />}>
                      <Row label="Pfad" value={
                        <code style={{ background: "rgba(0,0,0,0.2)", padding: "2px 6px", borderRadius: 3, fontSize: 11 }}>
                          {project.local_path}
                        </code>
                      } />
                      <Row label="Status" value={
                        project.local_available ? (
                          <span style={{ color: "var(--color-hermes-accent)", fontSize: 11 }}>
                            <CheckCircle2 size={12} style={{ verticalAlign: -1, marginRight: 3 }} /> verfuegbar
                          </span>
                        ) : (
                          <span style={{ color: "var(--color-hermes-danger)", fontSize: 11 }}>
                            <XCircle size={12} style={{ verticalAlign: -1, marginRight: 3 }} /> nicht verfuegbar
                          </span>
                        )
                      } />
                    </Section>
                  )}
                </div>
              )}

              {/* === TAB: Container === */}
              {activeTab === "components" && (
                <Section title={`Sub-Components (${project?.components?.length || 0})`} icon={<Boxes size={14} color="var(--color-hermes-accent-blue)" />}>
                  {project?.components && project.components.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                        Architektur-Hierarchie: <code style={{ background: "rgba(124,58,237,0.15)", padding: "1px 4px", borderRadius: 3 }}>
                          Projekt → Component → Container
                        </code>
                      </div>
                      {project.components.map((c) => (
                        <div key={c.id} style={{
                          padding: 10,
                          border: "1px solid var(--color-hermes-border)",
                          borderRadius: 6,
                          background: "rgba(88,166,255,0.03)",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                            <Container size={12} color="var(--color-hermes-accent-blue)" />
                            <span style={{ fontWeight: 600, fontSize: 12 }}>{c.name}</span>
                            <span style={{
                              fontSize: 9, padding: "1px 5px", borderRadius: 3,
                              background: "rgba(124,58,237,0.15)", color: "var(--color-hermes-accent-blue)",
                            }}>{c.slug}</span>
                            <span style={{
                              fontSize: 9, padding: "1px 5px", borderRadius: 3,
                              background: "rgba(46,160,67,0.15)", color: "var(--color-hermes-accent)",
                            }}>{c.type}</span>
                            <div style={{ flex: 1 }} />
                            <span style={{
                              fontSize: 9, fontWeight: 600,
                              color: c.container_status === "healthy" || c.container_status === "running"
                                ? "var(--color-hermes-accent)"
                                : "var(--color-hermes-danger)",
                            }}>
                              ● {c.container_status}
                            </span>
                          </div>
                          {c.description && (
                            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 6 }}>
                              {c.description}
                            </div>
                          )}
                          <div style={{ display: "flex", gap: 8, fontSize: 10, flexWrap: "wrap" }}>
                            {c.container_image && (
                              <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                                <Container size={9} />
                                <code style={{ background: "rgba(0,0,0,0.1)", padding: "1px 4px", borderRadius: 3 }}>
                                  {c.container_image}
                                </code>
                              </span>
                            )}
                            {c.container_port && (
                              <span style={{ color: "var(--color-hermes-text-secondary)" }}>
                                Port: <strong>{c.container_port}</strong>
                              </span>
                            )}
                            {c.container_name && (
                              <span style={{ color: "var(--color-hermes-text-secondary)" }}>
                                Name: <code>{c.container_name}</code>
                              </span>
                            )}
                            {c.container_count > 0 && (
                              <span style={{ color: "var(--color-hermes-accent)" }}>
                                {c.container_count} Container verknuepft
                              </span>
                            )}
                          </div>
                          <div style={{ display: "flex", gap: 8, fontSize: 10, marginTop: 6, flexWrap: "wrap" }}>
                            {c.local_path && (
                              <span>
                                <FolderOpen size={9} style={{ verticalAlign: -1, marginRight: 3 }} />
                                <code style={{ background: "rgba(0,0,0,0.1)", padding: "1px 4px", borderRadius: 3 }}>
                                  {c.local_path}
                                </code>
                              </span>
                            )}
                            {c.github_url && (
                              <a href={c.github_url} target="_blank" rel="noopener noreferrer"
                                 style={{ color: "var(--color-hermes-accent-blue)", textDecoration: "none" }}>
                                <FolderGit size={9} style={{ verticalAlign: -1, marginRight: 3 }} />
                                {c.github_url.replace("https://github.com/", "")}
                              </a>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ padding: 20, textAlign: "center", color: "var(--color-hermes-text-secondary)", fontSize: 11 }}>
                      Keine Sub-Components definiert.<br />
                      <span style={{ fontSize: 10 }}>
                        Components sind architektonische Sub-Einheiten unter diesem Projekt
                        (z.B. Pipeline, Frontend, NotebookLM).
                      </span>
                    </div>
                  )}
                </Section>
              )}

              {activeTab === "container" && (
                <Section title="Container-Info" icon={<Container size={14} />}>
                  {project.container_image ? (
                    <>
                      <Row label="Image" value={
                        <code style={{ background: "rgba(0,0,0,0.2)", padding: "2px 6px", borderRadius: 3, fontSize: 11 }}>
                          {project.container_image}
                        </code>
                      } />
                      <Row label="Externer Port" value={project.container_port || "?"} />
                      <Row label="Status" value={
                        <span style={{
                          color: project.container_status === "running" ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)",
                          fontSize: 11, fontWeight: 600,
                        }}>
                          ● {project.container_status || "unknown"}
                        </span>
                      } />
                    </>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                      Kein Container fuer dieses Projekt konfiguriert
                    </div>
                  )}
                </Section>
              )}

              {/* === TAB: Findings === */}
              {activeTab === "findings" && (
                <Section title="Kritische Findings" icon={<AlertTriangle size={14} color="var(--color-hermes-accent-orange)" />}>
                  {project.critical_findings && Object.keys(project.critical_findings).length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {Object.entries(project.critical_findings).map(([key, val]: [string, any]) => (
                        <div key={key} style={{
                          padding: 10, background: "rgba(220,38,38,0.08)",
                          border: "1px solid var(--color-hermes-danger)", borderRadius: 4,
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                            <AlertTriangle size={14} color="var(--color-hermes-danger)" />
                            <strong style={{ fontSize: 12, color: "var(--color-hermes-danger)" }}>
                              {key.replace(/_/g, "-").toUpperCase()}
                            </strong>
                          </div>
                          {typeof val === "object" && val !== null ? (
                            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", paddingLeft: 22 }}>
                              {Object.entries(val).map(([k, v]) => (
                                <div key={k}>
                                  <strong>{k}:</strong> {String(v)}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 11, paddingLeft: 22 }}>{String(val)}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                      Keine kritischen Findings dokumentiert
                    </div>
                  )}
                </Section>
              )}

              {/* === TAB: Tasks === */}
              {activeTab === "tasks" && (
                <Section title={`Tasks (${project.task_count})`} icon={<FileText size={14} />}>
                  {project.tasks && project.tasks.length > 0 ? (
                    <div style={{ maxHeight: 400, overflowY: "auto" }}>
                      {project.tasks.map(t => (
                        <div key={t.id} style={{
                          display: "flex", alignItems: "center", gap: 8, padding: "6px 8px",
                          borderBottom: "1px solid var(--color-hermes-border)", fontSize: 11,
                        }}>
                          <Hash size={10} color="var(--color-hermes-text-secondary)" style={{ flexShrink: 0 }} />
                          <span style={{
                            display: "inline-block", width: 70, fontSize: 10,
                            color: t.status === "done" ? "var(--color-hermes-accent)" :
                                   t.status === "triage" ? "var(--color-hermes-accent-blue)" :
                                   "var(--color-hermes-text-secondary)",
                            fontWeight: 600, textTransform: "uppercase",
                          }}>
                            {t.status}
                          </span>
                          <span style={{ flex: 1 }}>{t.title}</span>
                          <span style={{ color: "var(--color-hermes-text-secondary)", fontSize: 10 }}>
                            P{t.priority}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                      Keine Tasks fuer dieses Projekt
                    </div>
                  )}
                </Section>
              )}
            </>
          )}
        </div>

        {/* === Footer === */}
        <div style={{
          padding: "8px 16px", borderTop: "1px solid var(--color-hermes-border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          fontSize: 10, color: "var(--color-hermes-text-secondary)",
        }}>
          <span>
            <Database size={10} style={{ verticalAlign: -1, marginRight: 3 }} />
            Status: {project?.status || "?"}
            {" · "}
            Mode: {project?.category || "?"}
          </span>
          <span>ID: {projectId}</span>
        </div>
      </div>
    </div>
  )
}

// === Helper-Komponenten ===

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{
      background: "var(--color-hermes-muted)",
      borderRadius: 4, padding: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{ color: "var(--color-hermes-accent-blue)" }}>{icon}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--color-hermes-text)" }}>
          {title}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
      <span style={{ minWidth: 100, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", fontSize: 10 }}>
        {label}
      </span>
      <span style={{ flex: 1 }}>{value}</span>
    </div>
  )
}

function StatBadge({ icon, label, value }: { icon: React.ReactNode; label: string; value: any }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6, padding: "6px 10px",
      background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)",
      borderRadius: 4, fontSize: 11,
    }}>
      {icon}
      <span style={{ color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", fontSize: 9 }}>
        {label}
      </span>
      <span style={{ marginLeft: "auto", fontWeight: 600 }}>{value}</span>
    </div>
  )
}

// GitBranch-Icon (lucide-react hat das)
function GitBranchIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: -1 }}>
      <line x1="6" y1="3" x2="6" y2="15"></line>
      <circle cx="18" cy="6" r="3"></circle>
      <circle cx="6" cy="18" r="3"></circle>
      <path d="M18 9a9 9 0 0 1-9 9"></path>
    </svg>
  )
}
