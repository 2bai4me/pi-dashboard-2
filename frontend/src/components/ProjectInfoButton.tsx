import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Info, X, Plus, Trash2, Edit3, Save, XCircle,
  Database, FolderGit, Code2, AlertTriangle, Users, FileText,
  Lightbulb, Layers,
} from "lucide-react"

interface InfoEntry {
  id: number
  project_id: string
  info_type: string
  info_key: string
  info_value: string
  source: string
  confidence: number
  updated_by: string | null
  created_at: string | null
  updated_at: string | null
}

const TYPE_ICONS: Record<string, React.ReactElement> = {
  architecture: <Layers size={11} />,
  conventions: <Code2 size={11} />,
  dependencies: <Database size={11} />,
  components: <FolderGit size={11} />,
  contacts: <Users size={11} />,
  risks: <AlertTriangle size={11} />,
  decisions: <FileText size={11} />,
  context: <Lightbulb size={11} />,
  domain: <Lightbulb size={11} />,
}

const TYPE_COLORS: Record<string, string> = {
  architecture: "var(--color-hermes-accent-blue)",
  conventions: "var(--color-hermes-accent)",
  dependencies: "var(--color-hermes-accent-orange)",
  components: "var(--color-hermes-accent-blue)",
  contacts: "var(--color-hermes-accent)",
  risks: "var(--color-hermes-danger)",
  decisions: "var(--color-hermes-accent)",
  context: "var(--color-hermes-accent-orange)",
  domain: "var(--color-hermes-accent-blue)",
}

interface Props {
  projectId: string
  projectName: string
}

export default function ProjectInfoButton({ projectId, projectName }: Props) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [editValue, setEditValue] = useState("")
  const [newType, setNewType] = useState("context")
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")

  // Lade alle Info-Eintraege
  const { data: entries = [], isLoading, refetch } = useQuery({
    queryKey: ["project-info", projectId],
    queryFn: async () => {
      const r = await fetch(`/api/project-info/${projectId}`)
      if (!r.ok) throw new Error("Failed to load")
      return r.json() as Promise<InfoEntry[]>
    },
    enabled: open,
  })

  // Add entry
  const addMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch(`/api/project-info/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          info_type: newType,
          info_key: newKey,
          info_value: newValue,
          source: "manual",
          confidence: 100,
        }),
      })
      if (!r.ok) throw new Error("Add failed")
      return r.json()
    },
    onSuccess: () => {
      setNewKey(""); setNewValue("")
      queryClient.invalidateQueries({ queryKey: ["project-info", projectId] })
    },
  })

  // Update entry
  const updateMutation = useMutation({
    mutationFn: async ({ id, value }: { id: number; value: string }) => {
      const r = await fetch(`/api/project-info/${projectId}/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ info_value: value }),
      })
      if (!r.ok) throw new Error("Update failed")
      return r.json()
    },
    onSuccess: () => {
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ["project-info", projectId] })
    },
  })

  // Delete entry
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const r = await fetch(`/api/project-info/${projectId}/${id}`, { method: "DELETE" })
      if (!r.ok) throw new Error("Delete failed")
      return r.json()
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project-info", projectId] }),
  })

  // Gruppierung nach info_type
  const grouped = entries.reduce((acc, e) => {
    if (!acc[e.info_type]) acc[e.info_type] = []
    acc[e.info_type].push(e)
    return acc
  }, {} as Record<string, InfoEntry[]>)

  return (
    <>
      <button
        className="btn btn-sm"
        onClick={() => setOpen(true)}
        title={`Informationspaket fuer Projekt ${projectName} (Architektur, Conventions, Components, Risiken, ...)`}
        style={{
          background: "rgba(124,58,237,0.15)",
          border: "1px solid rgba(124,58,237,0.4)",
          color: "var(--color-hermes-accent-blue)",
          fontSize: 11,
          padding: "2px 6px",
        }}
      >
        <Info size={11} /> Info {entries.length > 0 && <span style={{ opacity: 0.7 }}>({entries.length})</span>}
      </button>

      {open && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "var(--color-hermes-bg)",
            border: "1px solid var(--color-hermes-border)",
            borderRadius: 8, width: 750, maxHeight: "85vh",
            display: "flex", flexDirection: "column",
          }}>
            {/* Header */}
            <div style={{
              padding: "12px 16px", borderBottom: "1px solid var(--color-hermes-border)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <Info size={16} color="var(--color-hermes-accent-blue)" />
              <h3 style={{ margin: 0, fontSize: 14, flex: 1 }}>
                Informationspaket: {projectName}
              </h3>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                {entries.length} Eintr\u00e4ge
              </span>
              <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", cursor: "pointer" }}>
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
              {isLoading ? (
                <div style={{ textAlign: "center", padding: 20, fontSize: 11 }}>Lade...</div>
              ) : entries.length === 0 ? (
                <div style={{ padding: 20, textAlign: "center", color: "var(--color-hermes-text-secondary)", fontSize: 11 }}>
                  Noch keine Info-Eintr\u00e4ge. Lege unten den ersten an oder starte eine Grill-Me-Session.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {Object.entries(grouped).map(([type, items]) => (
                    <div key={type}>
                      <div style={{
                        display: "flex", alignItems: "center", gap: 4, marginBottom: 4,
                        fontSize: 11, fontWeight: 600,
                        color: TYPE_COLORS[type] || "var(--color-hermes-text)",
                      }}>
                        {TYPE_ICONS[type] || <Info size={11} />}
                        {type} ({items.length})
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {items.map((e) => (
                          <div key={e.id} style={{
                            padding: 8,
                            background: "var(--color-hermes-muted)",
                            borderRadius: 4,
                            borderLeft: `3px solid ${TYPE_COLORS[e.info_type] || "var(--color-hermes-border)"}`,
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                              <strong style={{ fontSize: 11 }}>{e.info_key}</strong>
                              <span style={{
                                fontSize: 9, padding: "1px 4px", borderRadius: 3,
                                background: "rgba(0,0,0,0.1)",
                                color: "var(--color-hermes-text-secondary)",
                              }}>
                                {e.source}
                              </span>
                              <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>
                                conf={e.confidence}%
                              </span>
                              <div style={{ flex: 1 }} />
                              <button
                                onClick={() => { setEditing(e.id); setEditValue(e.info_value) }}
                                style={{ background: "none", border: "none", cursor: "pointer", padding: 2 }}
                                title="Bearbeiten"
                              >
                                <Edit3 size={11} />
                              </button>
                              <button
                                onClick={() => { if (confirm(`${e.info_key} l\u00f6schen?`)) deleteMutation.mutate(e.id) }}
                                style={{ background: "none", border: "none", cursor: "pointer", padding: 2, color: "var(--color-hermes-danger)" }}
                                title="L\u00f6schen"
                              >
                                <Trash2 size={11} />
                              </button>
                            </div>
                            {editing === e.id ? (
                              <div>
                                <textarea
                                  className="textarea"
                                  rows={2}
                                  value={editValue}
                                  onChange={(e) => setEditValue(e.target.value)}
                                  style={{ width: "100%", fontSize: 11, padding: 4 }}
                                />
                                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                                  <button
                                    className="btn btn-sm btn-primary"
                                    onClick={() => updateMutation.mutate({ id: e.id, value: editValue })}
                                    disabled={updateMutation.isPending}
                                  >
                                    <Save size={10} /> Speichern
                                  </button>
                                  <button className="btn btn-sm" onClick={() => setEditing(null)}>
                                    <XCircle size={10} /> Abbrechen
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ fontSize: 11, whiteSpace: "pre-wrap", color: "var(--color-hermes-text-secondary)" }}>
                                {e.info_value}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Add new */}
              <div style={{
                marginTop: 16, padding: 10,
                background: "rgba(124,58,237,0.05)",
                border: "1px solid rgba(124,58,237,0.2)",
                borderRadius: 6,
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>+ Neuer Eintrag</div>
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 4 }}>
                  <select
                    className="select"
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    style={{ fontSize: 11 }}
                  >
                    <option value="architecture">architecture</option>
                    <option value="conventions">conventions</option>
                    <option value="dependencies">dependencies</option>
                    <option value="components">components</option>
                    <option value="contacts">contacts</option>
                    <option value="risks">risks</option>
                    <option value="decisions">decisions</option>
                    <option value="context">context</option>
                    <option value="domain">domain</option>
                  </select>
                  <input
                    className="input"
                    placeholder="key (z.B. stack, render-engine, security-policy)"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                    style={{ fontSize: 11, padding: 4 }}
                  />
                </div>
                <textarea
                  className="textarea"
                  rows={2}
                  placeholder="Wert / Beschreibung..."
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  style={{ width: "100%", fontSize: 11, padding: 4, marginTop: 4 }}
                />
                <button
                  className="btn btn-sm btn-primary"
                  style={{ marginTop: 4 }}
                  onClick={() => addMutation.mutate()}
                  disabled={!newKey.trim() || !newValue.trim() || addMutation.isPending}
                >
                  <Plus size={11} /> Hinzuf\u00fcgen
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}