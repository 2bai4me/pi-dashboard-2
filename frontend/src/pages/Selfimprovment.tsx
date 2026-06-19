// Selfimprovment.tsx — Schwachstellen-Dokumentation + Subagent-Analyse
// User-Direktive 17.06.2026 (Prio 90 Feature)
//
// Workflow:
//  1. User dokumentiert Schwachstelle (Title, Description, Projekt PFLICHT)
//  2. Beim Anlegen startet SOFORT ein Subagent mit MiniMax M3
//  3. Subagent analysiert: root_cause + solution_proposal
//  4. User liest den Vorschlag, kann editieren
//  5. User kann Task aus Vorschlag erstellen (im richtigen Projekt/Board)
import { useState, useEffect, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Lightbulb, Plus, X, RefreshCw, FileText, CheckCircle2, AlertCircle, Clock, Edit3, Send, Copy } from "lucide-react"
import { api } from "../api"

const SEVERITIES = [
  { key: "low",      label: "Low",      color: "var(--color-hermes-text-secondary)" },
  { key: "medium",   label: "Medium",   color: "var(--color-hermes-accent-blue)" },
  { key: "high",     label: "High",     color: "var(--color-hermes-accent-orange)" },
  { key: "critical", label: "Critical", color: "var(--color-hermes-danger)" },
]

const CATEGORIES = [
  { key: "bug",      label: "Bug" },
  { key: "ui",       label: "UI" },
  { key: "perf",     label: "Performance" },
  { key: "security", label: "Security" },
  { key: "arch",     label: "Architecture" },
  { key: "other",    label: "Other" },
]

const STATUSES = [
  { key: "analyzing", label: "Analysing", color: "var(--color-hermes-accent-blue)", icon: Clock },
  { key: "done",      label: "Done",      color: "var(--color-hermes-accent)",     icon: CheckCircle2 },
  { key: "failed",    label: "Failed",    color: "var(--color-hermes-danger)",     icon: AlertCircle },
  { key: "reviewed",  label: "Reviewed",  color: "var(--color-hermes-text-secondary)", icon: CheckCircle2 },
]

function getSevColor(sev: string) {
  return SEVERITIES.find((s) => s.key === sev)?.color || "var(--color-hermes-text-secondary)"
}
function getStatusInfo(status: string) {
  return STATUSES.find((s) => s.key === status) || STATUSES[0]
}

export default function Selfimprovment() {
  const qc = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [selectedWeaknessId, setSelectedWeaknessId] = useState<string | null>(null)
  const [editingAnalysis, setEditingAnalysis] = useState(false)
  const [editRootCause, setEditRootCause] = useState("")
  const [editSolution, setEditSolution] = useState("")
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Projekte laden (fuer Projekt-Dropdown im Form)
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  })
  const projects: any[] = (projectsData as any)?.items || []
  const projectById: Record<string, any> = Object.fromEntries(projects.map((p) => [p.id, p]))

  // Schwachstellen laden
  const { data: weaknesses = [], isLoading } = useQuery({
    queryKey: ["weaknesses"],
    queryFn: () => api.listWeaknesses({ limit: 200 }),
    refetchInterval: 3000, // Auto-Refresh waehrend Subagent-Analyse laeuft
  })

  // Detail einer ausgewaehlten Schwaechstelle
  const { data: selectedWeakness } = useQuery({
    queryKey: ["weakness", selectedWeaknessId],
    queryFn: () => api.getWeakness(selectedWeaknessId!),
    enabled: !!selectedWeaknessId,
    refetchInterval: 3000,
  })

  function copyId(id: string) {
    navigator.clipboard.writeText(id)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1200)
  }

  return (
    <div>
      {/* === Header === */}
      <div className="page-header">
        <div className="workspace-header">
          <Lightbulb size={22} color="var(--color-hermes-accent-orange)" />
          <h1>Self-Improvement</h1>
        </div>
        <p>
          Dokumentierte Schwachstellen + automatische Subagent-Analyse (MiniMax M3).
          Aus jedem Vorschlag kann direkt ein Task im richtigen Projekt/Board erstellt werden.
        </p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={() => setShowAddForm(true)}>
          <Plus size={14} /> Schwachstelle dokumentieren
        </button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
          {weaknesses.length} Schwaechstelle{weaknesses.length !== 1 ? "n" : ""} dokumentiert
        </span>
      </div>

      {showAddForm && (
        <AddWeaknessForm
          projects={projects}
          onClose={() => setShowAddForm(false)}
          onSuccess={() => { setShowAddForm(false); qc.invalidateQueries({ queryKey: ["weaknesses"] }) }}
        />
      )}

      {/* === Tabelle === */}
      {isLoading ? (
        <div style={{ color: "var(--color-hermes-text-secondary)" }}>Lade Schwaechstellen…</div>
      ) : weaknesses.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
          <Lightbulb size={32} style={{ marginBottom: 8 }} />
          <p>Noch keine Schwaechstellen dokumentiert.</p>
          <p style={{ fontSize: 12 }}>
            Klicke <strong>Schwachstelle dokumentieren</strong>, um eine Schwachstelle anzulegen.
            Ein Subagent (MiniMax M3) analysiert sie automatisch.
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 100 }}>ID</th>
                <th>Schwachstelle</th>
                <th style={{ width: 130 }}>Projekt</th>
                <th style={{ width: 70 }}>Sev</th>
                <th style={{ width: 90 }}>Status</th>
                <th style={{ width: 110 }}>Analysiert</th>
                <th style={{ width: 100 }}>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {weaknesses.map((w: any) => {
                const sev = SEVERITIES.find((s) => s.key === w.severity)
                const st = getStatusInfo(w.status)
                const latest = w.analyses?.[0]
                const project = projectById[w.project_id]
                return (
                  <tr key={w.id} onClick={() => setSelectedWeaknessId(w.id)} style={{ cursor: "pointer" }}>
                    <td>
                      <span
                        className={`id-badge id-badge-board ${copiedId === w.id ? "id-badge-copied" : ""}`}
                        onClick={(e) => { e.stopPropagation(); copyId(w.id) }}
                        title={copiedId === w.id ? "Kopiert!" : `ID: ${w.id} — Klick zum Kopieren`}
                        style={{ fontSize: 9, padding: "1px 4px" }}
                      >
                        {copiedId === w.id ? "✓" : w.id.slice(0, 10)}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{w.title}</div>
                      <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2, maxWidth: 380, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {w.description}
                      </div>
                    </td>
                    <td>
                      {project ? (
                        <span style={{ fontSize: 11, color: "var(--color-hermes-accent-blue)" }}>
                          {project.name}
                        </span>
                      ) : (
                        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>unbekannt</span>
                      )}
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          fontSize: 10,
                          background: getSevColor(w.severity) + "33",
                          color: getSevColor(w.severity),
                          border: `1px solid ${getSevColor(w.severity)}`,
                        }}
                      >
                        {sev?.label || w.severity}
                      </span>
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          fontSize: 10,
                          background: st.color + "33",
                          color: st.color,
                          border: `1px solid ${st.color}`,
                        }}
                      >
                        {st.label}
                      </span>
                    </td>
                    <td>
                      {latest ? (
                        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                          {latest.status === "done" ? "✓ MiniMax M3" :
                           latest.status === "analyzing" ? "⏳ läuft" : "✗ failed"}
                        </span>
                      ) : (
                        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>—</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn-sm"
                        onClick={(e) => { e.stopPropagation(); setSelectedWeaknessId(w.id) }}
                        style={{ fontSize: 10, padding: "1px 6px" }}
                      >
                        <FileText size={10} /> Details
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* === Detail-Modal === */}
      {selectedWeaknessId && selectedWeakness && (
        <DetailModal
          weakness={selectedWeakness}
          project={projectById[selectedWeakness.project_id]}
          editingAnalysis={editingAnalysis}
          editRootCause={editRootCause}
          editSolution={editSolution}
          setEditingAnalysis={setEditingAnalysis}
          setEditRootCause={setEditRootCause}
          setEditSolution={setEditSolution}
          onClose={() => {
            setSelectedWeaknessId(null)
            setEditingAnalysis(false)
            qc.invalidateQueries({ queryKey: ["weaknesses"] })
          }}
          onReanalyze={() => qc.invalidateQueries({ queryKey: ["weakness", selectedWeaknessId] })}
          onCreateTask={() => qc.invalidateQueries({ queryKey: ["weaknesses"] })}
        />
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════
// Form: Schwachstelle anlegen
// ══════════════════════════════════════════════════════════════════════
function AddWeaknessForm({ projects, onClose, onSuccess }: { projects: any[]; onClose: () => void; onSuccess: () => void }) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [projectId, setProjectId] = useState(projects[0]?.id || "")
  const [severity, setSeverity] = useState("medium")
  const [category, setCategory] = useState("other")
  const [error, setError] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: () => api.createWeakness({ title, description, project_id: projectId, severity, category, created_by: "user" }),
    onSuccess: () => onSuccess(),
    onError: (e: any) => setError(e.message || "Fehler beim Anlegen"),
  })

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 520, maxWidth: 640 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Plus size={18} color="var(--color-hermes-accent-blue)" />
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Schwachstelle dokumentieren</h3>
          <div style={{ flex: 1 }} />
          <button className="btn btn-sm" onClick={onClose}><X size={12} /></button>
        </div>
        <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "0 0 12px" }}>
          Sobald du speicherst, startet automatisch ein Subagent (MiniMax M3) mit der Ursachenanalyse.
        </p>
        <input
          className="input mb-2"
          placeholder="Titel der Schwaechstelle (kurz & praegnant)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          autoFocus
        />
        <textarea
          className="input mb-2"
          placeholder="Beschreibung: Was ist passiert? Welche Dateien/Komponenten sind betroffen? Wie reproduzierbar?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          style={{ minHeight: 100, fontFamily: "var(--font-mono)", fontSize: 12 }}
        />
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
          <select className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.length === 0 && <option value="">(kein Projekt)</option>}
            {projects.map((p: any) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            {SEVERITIES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
        {error && <div style={{ padding: 8, background: "var(--color-hermes-danger)", color: "#fff", borderRadius: 4, fontSize: 11, marginBottom: 8 }}>⚠ {error}</div>}
        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 8 }}>
          Projekt: <strong>PFLICHT</strong> — bestimmt, in welches Board der spaetere Task eingestellt wird.
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button
            className="btn btn-primary"
            onClick={() => {
              setError(null)
              if (!title.trim()) { setError("Titel ist erforderlich"); return }
              if (!description.trim()) { setError("Beschreibung ist erforderlich"); return }
              if (!projectId) { setError("Projekt ist PFLICHT (User-Direktive 17.06.2026)"); return }
              createMut.mutate()
            }}
            disabled={createMut.isPending}
            style={{ background: "linear-gradient(135deg, #d29922 0%, #f0883e 100%)", borderColor: "var(--color-hermes-accent-orange)" }}
          >
            {createMut.isPending ? "⏳ Erstelle..." : (
              <>
                <Lightbulb size={12} /> Dokumentieren + Subagent starten
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════
// Detail-Modal: Loesungsvorschlag lesen/editieren + Task erstellen
// ══════════════════════════════════════════════════════════════════════
function DetailModal({ weakness, project, editingAnalysis, editRootCause, editSolution, setEditingAnalysis, setEditRootCause, setEditSolution, onClose, onReanalyze, onCreateTask }: any) {
  const qc = useQueryClient()
  const [editingWeakness, setEditingWeakness] = useState(false)
  const [editTitle, setEditTitle] = useState(weakness.title)
  const [editDesc, setEditDesc] = useState(weakness.description)

  const latest = weakness.analyses?.[0]

  const updateMut = useMutation({
    mutationFn: () => api.updateWeakness(weakness.id, { title: editTitle, description: editDesc }),
    onSuccess: () => {
      setEditingWeakness(false)
      qc.invalidateQueries({ queryKey: ["weakness", weakness.id] })
      qc.invalidateQueries({ queryKey: ["weaknesses"] })
    },
  })
  const reanalyzeMut = useMutation({
    mutationFn: () => api.reanalyzeWeakness(weakness.id),
    onSuccess: () => onReanalyze(),
  })
  const editAnalysisMut = useMutation({
    mutationFn: (data: any) => api.editAnalysis(latest.id, data),
    onSuccess: () => {
      setEditingAnalysis(false)
      qc.invalidateQueries({ queryKey: ["weakness", weakness.id] })
    },
  })
  const createTaskMut = useMutation({
    mutationFn: () => api.createTaskFromWeakness(weakness.id),
    onSuccess: (result: any) => {
      onCreateTask()
      alert(`Task erstellt!\n\nID: ${result.task_id}\nTitle: ${result.task.title}\nProjekt: ${project?.name || weakness.project_id}\n\nTask ist im Board sichtbar (Cache-Invalidation aktiv).`)
    },
  })

  function startEditAnalysis() {
    setEditRootCause(latest?.root_cause || "")
    setEditSolution(latest?.solution_proposal || "")
    setEditingAnalysis(true)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 720, maxWidth: 920, maxHeight: "90vh", overflow: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Lightbulb size={18} color="var(--color-hermes-accent-orange)" />
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Self-Improvement Detail</h3>
          <div style={{ flex: 1 }} />
          <button className="btn btn-sm" onClick={onClose}><X size={12} /></button>
        </div>

        {/* Schwachstelle */}
        <div className="card mb-2">
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <strong style={{ fontSize: 13 }}>Schwaechstelle</strong>
            <span className={`id-badge id-badge-board`} title={`ID: ${weakness.id}`} style={{ fontSize: 9, padding: "1px 4px" }}>
              {weakness.id.slice(0, 10)}
            </span>
            <span className="badge" style={{ fontSize: 10, background: getSevColor(weakness.severity) + "33", color: getSevColor(weakness.severity) }}>
              {weakness.severity}
            </span>
            <span className="badge badge-gray" style={{ fontSize: 10 }}>{weakness.category}</span>
            <div style={{ flex: 1 }} />
            {!editingWeakness ? (
              <button className="btn btn-sm" onClick={() => setEditingWeakness(true)} style={{ fontSize: 10, padding: "1px 6px" }}>
                <Edit3 size={10} /> Bearbeiten
              </button>
            ) : (
              <div style={{ display: "flex", gap: 4 }}>
                <button className="btn btn-sm" onClick={() => updateMut.mutate()} disabled={updateMut.isPending} style={{ fontSize: 10, padding: "1px 6px" }}>
                  Speichern
                </button>
                <button className="btn btn-sm" onClick={() => { setEditTitle(weakness.title); setEditDesc(weakness.description); setEditingWeakness(false) }} style={{ fontSize: 10, padding: "1px 6px" }}>
                  Abbrechen
                </button>
              </div>
            )}
          </div>
          {editingWeakness ? (
            <>
              <input className="input mb-2" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
              <textarea className="input" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} style={{ minHeight: 80, fontFamily: "var(--font-mono)", fontSize: 12 }} />
            </>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>{weakness.title}</div>
              <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{weakness.description}</div>
            </>
          )}
          <div style={{ marginTop: 8, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
            <strong>Projekt:</strong> {project?.name || weakness.project_id}
            {" · "}
            <strong>Erkannt:</strong> {weakness.created_at ? new Date(weakness.created_at).toLocaleString("de-DE") : "—"}
            {" · "}
            <strong>Status:</strong> {getStatusInfo(weakness.status).label}
          </div>
        </div>

        {/* Subagent-Analyse */}
        <div className="card mb-2" style={{ borderLeft: `3px solid var(--color-hermes-accent-blue)` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>Subagent-Analyse (MiniMax M3)</strong>
            {latest && (
              <span className="badge" style={{ fontSize: 10, background: getStatusInfo(latest.status).color + "33", color: getStatusInfo(latest.status).color }}>
                {getStatusInfo(latest.status).label}
              </span>
            )}
            <div style={{ flex: 1 }} />
            <button
              className="btn btn-sm"
              onClick={() => reanalyzeMut.mutate()}
              disabled={reanalyzeMut.isPending}
              title="Erneut analysieren (neue Subagent-Anfrage)"
              style={{ fontSize: 10, padding: "2px 6px" }}
            >
              <RefreshCw size={10} className={reanalyzeMut.isPending ? "spin" : ""} /> Neu analysieren
            </button>
          </div>

          {!latest ? (
            <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12, padding: 12, textAlign: "center" }}>
              Noch keine Analyse vorhanden.
            </div>
          ) : latest.status === "analyzing" ? (
            <div style={{ padding: 16, textAlign: "center" }}>
              <div className="spin" style={{ display: "inline-block", fontSize: 20 }}>⏳</div>
              <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 8 }}>
                Subagent (MiniMax M3) analysiert die Schwachstelle…<br/>
                <span style={{ fontSize: 10 }}>Dauert ca. 30-120 Sekunden. Diese Seite aktualisiert sich automatisch.</span>
              </p>
            </div>
          ) : latest.status === "failed" ? (
            <div style={{ padding: 12, background: "rgba(248,81,73,0.1)", borderRadius: 4, fontSize: 11 }}>
              <strong style={{ color: "var(--color-hermes-danger)" }}>Analyse fehlgeschlagen</strong>
              <pre style={{ marginTop: 6, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{latest.error || "Unbekannter Fehler"}</pre>
            </div>
          ) : (
            <>
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                  Ursachenanalyse
                </div>
                {editingAnalysis ? (
                  <textarea
                    className="input"
                    value={editRootCause}
                    onChange={(e) => setEditRootCause(e.target.value)}
                    style={{ minHeight: 100, fontFamily: "var(--font-mono)", fontSize: 12 }}
                  />
                ) : (
                  <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", margin: 0, padding: 10, background: "var(--color-hermes-muted)", borderRadius: 4, lineHeight: 1.5 }}>
                    {latest.root_cause || "(leer)"}
                  </pre>
                )}
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", fontSize: 10, color: "var(--color-hermes-text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                  <span>Lösungsvorschlag</span>
                  <div style={{ flex: 1 }} />
                  {!editingAnalysis ? (
                    <button className="btn btn-sm" onClick={startEditAnalysis} style={{ fontSize: 10, padding: "1px 6px" }}>
                      <Edit3 size={10} /> Vorschlag bearbeiten
                    </button>
                  ) : (
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        className="btn btn-sm"
                        onClick={() => editAnalysisMut.mutate({ root_cause: editRootCause, solution_proposal: editSolution })}
                        disabled={editAnalysisMut.isPending}
                        style={{ fontSize: 10, padding: "1px 6px" }}
                      >
                        Speichern
                      </button>
                      <button className="btn btn-sm" onClick={() => setEditingAnalysis(false)} style={{ fontSize: 10, padding: "1px 6px" }}>
                        Abbrechen
                      </button>
                    </div>
                  )}
                </div>
                {editingAnalysis ? (
                  <textarea
                    className="input"
                    value={editSolution}
                    onChange={(e) => setEditSolution(e.target.value)}
                    style={{ minHeight: 200, fontFamily: "var(--font-mono)", fontSize: 12 }}
                  />
                ) : (
                  <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", margin: 0, padding: 10, background: "var(--color-hermes-muted)", borderRadius: 4, lineHeight: 1.5, maxHeight: 240, overflow: "auto" }}>
                    {latest.solution_proposal || "(leer)"}
                  </pre>
                )}
              </div>
            </>
          )}
        </div>

        {/* Aktionen */}
        {latest && latest.status === "done" && latest.solution_proposal && (
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button
              className="btn btn-primary"
              onClick={() => createTaskMut.mutate()}
              disabled={createTaskMut.isPending}
              style={{
                background: "linear-gradient(135deg, #2ea043 0%, #58a6ff 100%)",
                fontWeight: 600,
                fontSize: 12,
              }}
            >
              {createTaskMut.isPending ? "⏳ Erstelle Task..." : (
                <>
                  <Send size={12} /> Task aus Vorschlag erstellen
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
