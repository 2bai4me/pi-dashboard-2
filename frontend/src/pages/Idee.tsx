// Idee.tsx — Ideen-Verwaltung: Liste, Erstellen, Bearbeiten, Speichern, Loeschen, Umsetzen
// User-Direktive 23.06.2026 (Task db83ed4bb5a1):
//   - Neu-Button analog zu Projekten/SOPs
//   - Drei Action-Buttons am Ende von Requirements: Speichern, Loeschen, Umsetzen

import { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Sparkles, ClipboardList, Lightbulb, Plus, Trash2, Send, Save, ArrowLeft,
} from "lucide-react"
import { api } from "../api"

type IdeeTab = "brainstorm" | "requirements"

interface Idea {
  id: string
  title: string
  description?: string
  brainstorm?: string
  requirements?: string
  status: string
  tags?: string[]
  created_at?: string
  updated_at?: string
}

export default function Idee() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTab = (searchParams.get("tab") as IdeeTab) || "brainstorm"
  const initialIdeaId = searchParams.get("id")
  const [tab, setTab] = useState<IdeeTab>(initialTab)
  const [selectedIdeaId, setSelectedIdeaId] = useState<string | null>(initialIdeaId)
  const [showNewForm, setShowNewForm] = useState(false)
  const qc = useQueryClient()

  // Liste aller Ideen
  const { data: ideasData, isLoading } = useQuery({
    queryKey: ["ideas"],
    queryFn: () => (api as any).ideas?.list() ?? Promise.resolve([]),
  })
  const ideas: Idea[] = (ideasData as any) || []

  // Wenn keine Idee gewaehlt UND Liste nicht leer: erste Idee waehlen
  useEffect(() => {
    if (!selectedIdeaId && ideas.length > 0) {
      setSelectedIdeaId(ideas[0].id)
    }
  }, [ideas, selectedIdeaId])

  function setTabAndUrl(t: IdeeTab) {
    setTab(t)
    const params: Record<string, string> = { tab: t }
    if (selectedIdeaId) params.id = selectedIdeaId
    setSearchParams(params)
  }

  function selectIdea(id: string) {
    setSelectedIdeaId(id)
    setShowNewForm(false)
    setSearchParams({ tab, id })
  }

  function showOverview() {
    setSelectedIdeaId(null)
    setShowNewForm(false)
    setSearchParams({})
  }

  // Uebersicht (Liste + Neu-Button)
  if (!selectedIdeaId && !showNewForm) {
    return (
      <div>
        <div className="page-header">
          <div className="workspace-header">
            <Lightbulb size={20} color="var(--color-hermes-accent)" />
            <h1>Idee</h1>
          </div>
          <p>Brainstorming & Requirements — der kreative Bereich vor der Umsetzung.</p>
        </div>

        <button
          className="btn btn-primary mb-3"
          onClick={() => setShowNewForm(true)}
        >
          <Plus size={14} /> Neu
        </button>

        {isLoading ? (
          <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
            Lade Ideen...
          </div>
        ) : ideas.length === 0 ? (
          <div className="card" style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
            Noch keine Ideen. Klicke <strong>+ Neu</strong> um zu starten.
          </div>
        ) : (
          <div className="card-grid">
            {ideas.map((idea) => (
              <div
                key={idea.id}
                className="project-card"
                onClick={() => selectIdea(idea.id)}
                style={{
                  borderLeftColor: idea.status === "converted"
                    ? "var(--color-hermes-accent)"
                    : "var(--color-hermes-text-secondary)",
                }}
              >
                <div className="project-card-name">{idea.title}</div>
                <div className="project-card-desc">
                  {(idea.description || idea.brainstorm || "(keine Beschreibung)").slice(0, 100)}
                </div>
                <div className="project-card-meta">
                  <span className="badge badge-gray">{idea.status}</span>
                  <span>· Updated: {idea.updated_at
                    ? new Date(idea.updated_at).toLocaleDateString("de-DE")
                    : "-"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Neue-Idee-Formular
  if (showNewForm) {
    return <NewIdeaForm onCancel={showOverview} onCreated={(id) => selectIdea(id)} />
  }

  // Editor fuer bestehende Idee
  const current = ideas.find((i) => i.id === selectedIdeaId)
  if (!current) {
    return (
      <div className="card">
        <p>Idee nicht gefunden.</p>
        <button className="btn" onClick={showOverview}>
          <ArrowLeft size={14} /> Zurueck zur Uebersicht
        </button>
      </div>
    )
  }

  return (
    <IdeaEditor
      idea={current}
      activeTab={tab}
      onTabChange={setTabAndUrl}
      onBack={showOverview}
      onDeleted={showOverview}
    />
  )
}

// === New-Idea-Formular ===

function NewIdeaForm({ onCancel, onCreated }: {
  onCancel: () => void
  onCreated: (id: string) => void
}) {
  const qc = useQueryClient()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [tagsInput, setTagsInput] = useState("")

  const createMut = useMutation({
    mutationFn: async () => {
      const tags = tagsInput.split(",").map((t) => t.trim()).filter(Boolean)
      return (api as any).ideas.create({
        title, description, tags, status: "draft",
      })
    },
    onSuccess: (idea: Idea) => {
      qc.invalidateQueries({ queryKey: ["ideas"] })
      onCreated(idea.id)
    },
  })

  return (
    <div>
      <div className="page-header">
        <button className="btn btn-sm" onClick={onCancel} style={{ marginBottom: 8 }}>
          <ArrowLeft size={12} /> Zurueck
        </button>
        <h1>Neue Idee</h1>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          Titel *
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="z.B. Multi-Agent-Swarm fuer komplexe Tasks"
            autoFocus
          />
        </label>
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          Beschreibung
          <textarea
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Kurze Beschreibung der Idee..."
          />
        </label>
        <label style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
          Tags (kommasepariert)
          <input
            className="input"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="z.B. swarm, ai, backend"
          />
        </label>
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <button
            className="btn btn-primary"
            disabled={!title.trim() || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            <Save size={14} /> {createMut.isPending ? "Erstelle..." : "Erstellen"}
          </button>
          <button className="btn" onClick={onCancel}>
            Abbrechen
          </button>
        </div>
        {createMut.isError && (
          <div style={{ color: "var(--color-hermes-danger)", fontSize: 12, marginTop: 8 }}>
            Fehler: {(createMut.error as any)?.message || "Unbekannt"}
          </div>
        )}
      </div>
    </div>
  )
}

// === Idea-Editor mit Sub-Tabs ===

function IdeaEditor({ idea, activeTab, onTabChange, onBack, onDeleted }: {
  idea: Idea
  activeTab: IdeeTab
  onTabChange: (t: IdeeTab) => void
  onBack: () => void
  onDeleted: () => void
}) {
  const qc = useQueryClient()
  const [brainstorm, setBrainstorm] = useState(idea.brainstorm || "")
  const [requirements, setRequirements] = useState(idea.requirements || "")

  // Reset bei Ideen-Wechsel
  useEffect(() => {
    setBrainstorm(idea.brainstorm || "")
    setRequirements(idea.requirements || "")
  }, [idea.id])

  const saveMut = useMutation({
    mutationFn: async () => {
      return (api as any).ideas.update(idea.id, {
        title: idea.title,
        brainstorm,
        requirements,
        status: "saved",
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ideas"] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: async () => {
      return (api as any).ideas.delete(idea.id)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ideas"] })
      onDeleted()
    },
  })

  const convertMut = useMutation({
    mutationFn: async () => {
      return (api as any).ideas.convertToTask(idea.id)
    },
    onSuccess: (result: any) => {
      qc.invalidateQueries({ queryKey: ["ideas"] })
      qc.invalidateQueries({ queryKey: ["tasks"] })
      alert(`Idee umgesetzt: Task ${result.task_id} wurde erstellt`)
    },
  })

  return (
    <div>
      <div className="page-header">
        <button className="btn btn-sm" onClick={onBack} style={{ marginBottom: 8 }}>
          <ArrowLeft size={12} /> Zurueck zur Uebersicht
        </button>
        <h1>{idea.title}</h1>
        <span className="badge badge-gray" style={{ marginLeft: 8 }}>{idea.status}</span>
      </div>

      <div className="subtab-bar">
        <button
          className={`subtab ${activeTab === "brainstorm" ? "active" : ""}`}
          onClick={() => onTabChange("brainstorm")}
        >
          <Sparkles size={14} /> Brainstorm
        </button>
        <button
          className={`subtab ${activeTab === "requirements" ? "active" : ""}`}
          onClick={() => onTabChange("requirements")}
        >
          <ClipboardList size={14} /> Requirements
        </button>
      </div>

      {activeTab === "brainstorm" && (
        <div className="card">
          <textarea
            className="input"
            value={brainstorm}
            onChange={(e) => setBrainstorm(e.target.value)}
            rows={20}
            placeholder="Brainstorming-Notizen, wilde Ideen, Skizzen..."
            style={{ fontFamily: "var(--font-mono)", minHeight: 400 }}
          />
        </div>
      )}

      {activeTab === "requirements" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <textarea
            className="input"
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
            rows={20}
            placeholder="Anforderungen, Akzeptanzkriterien, User Stories..."
            style={{ fontFamily: "var(--font-mono)", minHeight: 400 }}
          />

          {/* User-Direktive 23.06.2026: 3 Action-Buttons am Ende */}
          <div style={{ display: "flex", gap: 8, marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--color-hermes-border)" }}>
            <button
              className="btn btn-primary"
              disabled={saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              <Save size={14} /> Idee speichern
            </button>
            <button
              className="btn"
              disabled={convertMut.isPending}
              onClick={() => {
                if (confirm(`Idee "${idea.title}" als Task im PI Dashboard 2 umsetzen?`)) {
                  convertMut.mutate()
                }
              }}
            >
              <Send size={14} /> Idee umsetzen
            </button>
            <button
              className="btn"
              style={{ color: "var(--color-hermes-danger)" }}
              disabled={deleteMut.isPending}
              onClick={() => {
                if (confirm(`Idee "${idea.title}" wirklich loeschen?`)) {
                  deleteMut.mutate()
                }
              }}
            >
              <Trash2 size={14} /> Idee loeschen
            </button>
            <div style={{ flex: 1 }} />
            {(saveMut.isSuccess || deleteMut.isSuccess || convertMut.isSuccess) && (
              <span className="badge badge-green" style={{ alignSelf: "center" }}>
                {saveMut.isSuccess ? "gespeichert" :
                 deleteMut.isSuccess ? "geloescht" :
                 convertMut.isSuccess ? "umgesetzt" : ""}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}