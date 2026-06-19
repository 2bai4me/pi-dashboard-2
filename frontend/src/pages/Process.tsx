import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { api } from "../api"
import { ProcessDesigner } from "../components/ProcessDesigner"
import { Plus, Trash2, GitBranch, ArrowLeft, RefreshCw, Power, PowerOff } from "lucide-react"

export default function Process() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const projectId = searchParams.get("projectId")
  const templateId = searchParams.get("templateId")

  const { data: templates = [] } = useQuery({
    queryKey: ["process-templates", projectId],
    queryFn: () => api.listProcessTemplates(projectId || undefined),
    enabled: !!projectId,
  })
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  })
  const projects = (projectsData as any)?.items || []
  const { data: tasksData } = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api.listTasks({ project_id: projectId || undefined, limit: 200 }),
    enabled: !!projectId,
  })
  const tasks = (tasksData as any)?.items || []

  const createMut = useMutation({
    mutationFn: (data: any) => api.createProcessTemplate(data),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["process-templates", projectId] })
      setSearchParams({ projectId: projectId!, templateId: t.id })
    },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => api.updateProcessTemplate(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["process-templates", projectId] }),
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteProcessTemplate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["process-templates", projectId] })
      setSearchParams({ projectId: projectId! })
    },
  })
  const activateMut = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => api.activateProcessTemplate(id, projectId!, note),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["process-templates", projectId] })
      qc.invalidateQueries({ queryKey: ["active-template", projectId] })
      alert(`✅ Template freigeschaltet!\n\n${r.message}\n\nAb sofort folgen alle Tasks dieses Projekts den Edges des Templates.`)
    },
  })
  const deactivateMut = useMutation({
    mutationFn: (id: string) => api.deactivateProcessTemplate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["process-templates", projectId] })
      qc.invalidateQueries({ queryKey: ["active-template", projectId] })
    },
  })
  const applyMut = useMutation({
    mutationFn: ({ tid, taskId }: { tid: string; taskId: string }) => api.applyProcessTemplate(tid, taskId),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["tasks", projectId] })
      alert(`${result.total} Sub-Tasks erstellt!`)
    },
  })

  // Waehle aktives Template
  const activeTemplate = templateId ? templates.find((t: any) => t.id === templateId) : null

  function handleSave(data: any) {
    if (activeTemplate) {
      updateMut.mutate({ id: activeTemplate.id, data })
    } else {
      createMut.mutate({ ...data, project_id: projectId })
    }
  }

  function newTemplate() {
    if (!projectId) {
      alert("Bitte zuerst ein Projekt auswaehlen")
      return
    }
    const name = prompt("Name fuer neues Process-Template:", "Neuer Prozess")
    if (!name) return
    createMut.mutate({
      project_id: projectId,
      name,
      nodes: [
        { id: "start1", type: "start", label: "Start", x: 100, y: 100, properties: { is_marker: true } },
        { id: "end1", type: "end", label: "Ende", x: 100, y: 400, properties: { is_marker: true } },
      ],
      edges: [],
    })
  }

  if (!projectId) {
    return (
      <div>
        <div className="page-header">
          <h1>Process Designer (BPMN 2.0)</h1>
          <p>Bitte zuerst ein Projekt auswaehlen</p>
        </div>
        <div className="card-grid">
          {projects.map((p: any) => (
            <div key={p.id} className="project-card" onClick={() => setSearchParams({ projectId: p.id })}>
              <div className="project-card-name">{p.name}</div>
              <div className="project-card-desc">{p.description || "(keine Beschreibung)"}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)" }}>
      {/* Top-Bar: Projekt + Template-Auswahl */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", borderBottom: "1px solid var(--color-hermes-border)", background: "var(--color-hermes-surface)" }}>
        <button className="btn btn-sm" onClick={() => setSearchParams({})} title="Projekte">
          <ArrowLeft size={12} /> Projekte
        </button>
        <span className="badge badge-blue" style={{ fontSize: 10 }}>
          {projects.find((p: any) => p.id === projectId)?.name || projectId}
        </span>
        <div style={{ width: 1, height: 20, background: "var(--color-hermes-border)", margin: "0 8px" }} />
        <select
          className="select"
          value={templateId || ""}
          onChange={(e) => setSearchParams({ projectId, templateId: e.target.value || "" })}
          style={{ fontSize: 12, minWidth: 200 }}
        >
          <option value="">-- Template waehlen --</option>
          {templates.map((t: any) => (
            <option key={t.id} value={t.id}>{t.name} ({t.node_count} steps)</option>
          ))}
        </select>
        <button className="btn btn-primary btn-sm" onClick={newTemplate}>
          <Plus size={12} /> Neues Template
        </button>
        {activeTemplate && (
          <>
            <button className="btn btn-sm" onClick={() => setSearchParams({ projectId, templateId: "" })}>
              <RefreshCw size={12} /> Neues
            </button>
            {activeTemplate.is_active ? (
              <button className="btn btn-sm" onClick={() => {
                if (confirm(`Template "${activeTemplate.name}" deaktivieren? Tasks laufen dann wieder nach Standard-Workflow.`)) {
                  deactivateMut.mutate(activeTemplate.id)
                }
              }} style={{ background: "rgba(248, 81, 73, 0.15)", color: "var(--color-hermes-danger)", borderColor: "var(--color-hermes-danger)" }}>
                <PowerOff size={12} /> Deaktivieren
              </button>
            ) : (
              <button className="btn btn-sm" onClick={() => {
                const note = prompt("Aktivierungs-Notiz (optional):", "Standard-Workflow wird vom Template gesteuert")
                activateMut.mutate({ id: activeTemplate.id, note: note || undefined })
              }} style={{ background: "rgba(46, 160, 67, 0.15)", color: "var(--color-hermes-accent)", borderColor: "var(--color-hermes-accent)" }}>
                <Power size={12} /> Freischalten
              </button>
            )}
            <button className="btn btn-sm btn-danger" onClick={() => {
              if (confirm(`Process-Template "${activeTemplate.name}" wirklich loeschen?`)) {
                deleteMut.mutate(activeTemplate.id)
              }
            }}>
              <Trash2 size={12} /> Loeschen
            </button>
            <div style={{ flex: 1 }} />
            {activeTemplate.is_active && (
              <span className="badge badge-green" style={{ fontSize: 10 }}>● AKTIV</span>
            )}
            <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              Letzte Aenderung: {activeTemplate.updated_at ? new Date(activeTemplate.updated_at).toLocaleString("de-DE") : "-"}
            </span>
          </>
        )}
      </div>

      {/* Templates-Liste (wenn keiner gewaehlt) */}
      {!activeTemplate && (
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          <div className="page-header">
            <h1>Process-Templates</h1>
            <p>Designer Prozesse die als Vorlage fuer Tasks dienen</p>
          </div>
          {templates.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 40 }}>
              <GitBranch size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
              <p style={{ color: "var(--color-hermes-text-secondary)" }}>Noch keine Templates. Klicke "Neues Template".</p>
            </div>
          ) : (
            <div className="card-grid">
              {templates.map((t: any) => (
                <div key={t.id} className="card" style={{ cursor: "pointer" }} onClick={() => setSearchParams({ projectId, templateId: t.id })}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <GitBranch size={16} color="var(--color-hermes-accent-blue)" />
                    <strong style={{ flex: 1 }}>{t.name}</strong>
                    {t.is_active && <span className="badge badge-green" style={{ fontSize: 10 }}>● AKTIV</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 8 }}>
                    {t.description || "(keine Beschreibung)"}
                  </div>
                  <div style={{ display: "flex", gap: 6, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                    <span className="badge badge-blue">{t.node_count} Schritte</span>
                    <span className="badge badge-gray">{t.edge_count} Verbindungen</span>
                    {(t.edges || []).filter((e: any) => e.target_status).length > 0 && (
                      <span className="badge badge-orange">⚡ {(t.edges || []).filter((e: any) => e.target_status).length} Status-Override</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Designer (wenn Template gewaehlt) */}
      {activeTemplate && (
        <div style={{ flex: 1 }}>
          <ProcessDesigner
            template={{
              id: activeTemplate.id,
              project_id: activeTemplate.project_id,
              name: activeTemplate.name,
              description: activeTemplate.description,
              nodes: activeTemplate.nodes || [],
              edges: activeTemplate.edges || [],
            }}
            onSave={handleSave}
            isSaving={updateMut.isPending || createMut.isPending}
            availableTasks={tasks}
            onApplyToTask={(taskId) => applyMut.mutate({ tid: activeTemplate.id, taskId })}
          />
        </div>
      )}
    </div>
  )
}
